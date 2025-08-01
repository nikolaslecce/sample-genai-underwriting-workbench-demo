import json
import boto3
import os
import base64
import io
import urllib.parse
from pdf2image import convert_from_path
from datetime import datetime, timezone
import re

# Initialize AWS clients outside the handler for reuse
s3 = boto3.client('s3')
bedrock_runtime = boto3.client(service_name='bedrock-runtime')
dynamodb_client = boto3.client('dynamodb')
jobs_table_name = os.environ.get('JOBS_TABLE_NAME')
BATCH_SIZE = 3


def get_extraction_prompt(document_type, insurance_type, page_numbers, previous_analysis_json="{}"):
    """Get the appropriate extraction prompt for a batch of pages, considering previous analysis."""
    
    # Base prompt
    base_prompt = f"""You are an underwriting assistant analyzing pages {page_numbers} from a document submission.
The overall document has been classified as: {document_type}
The insurance type is: {insurance_type}

Analysis of previous pages (if any):
```json
{previous_analysis_json}
```

**Your Task:**
1. For each new page image provided in this batch, perform two tasks:
    a. **Classify the page**: Identify a specific sub-document type for the page (e.g., "Applicant Information", "Medical History", "Attending Physician Statement", "Lab Results", "Prescription History").
    b. **Extract all data**: Extract all key-value pairs of information from the page.
2. **Structure your output**: Group the extracted data for each page under its classified sub-document type.
3. **Maintain Consistency**: If a page's type matches a key from the "Analysis of previous pages", you will group it with those pages. If it's a new type, you will create a new key.
4. **Return ONLY a JSON object** that contains the analysis for the **CURRENT BATCH of pages**. Do not repeat the `previous_analysis_json` in your output.

**Important Guidelines:**
- The keys in your JSON output should be the sub-document types.
- The values should be a list of page objects.
- Each page object must include a `"page_number"` and all other data you extracted.
- If a page is blank or contains no extractable information, return an object with just the page number and a note, like `{{"page_number": 1, "status": "No information found"}}`.
- Do not include any explanations or text outside of the final JSON object.

**Example Output Format:**
```json
{{
  "Applicant Information": [
    {{
      "page_number": 1,
      "full_name": "John Doe",
      "date_of_birth": "1980-01-15",
      "address": "123 Main St, Anytown, USA"
    }}
  ],
  "Medical History": [
    {{
      "page_number": 2,
      "condition": "Hypertension",
      "diagnosed_date": "2015-06-20",
      "treatment": "Lisinopril"
    }}
  ]
}}
```

Here come the images for pages {page_numbers}:
"""
    return base_prompt


def lambda_handler(event, context):
    print("Received event:", json.dumps(event))
    
    # Initialize variables
    bucket = None
    key = None 
    encoded_key = None 
    download_path = None
    document_type = None
    all_extracted_data = {}
    extraction_result = {"status": "ERROR", "message": "Processing not completed", "data": {}}
    job_id = None
    
    try:
        # --- Step 1: Extract input parameters from the event ---
        try:
            bucket = event['detail']['bucket']['name']
            encoded_key = event['detail']['object']['key'] 
            key = urllib.parse.unquote_plus(encoded_key)
            print(f"Event: {event}")
            job_id = event.get('classification').get('jobId')
            document_type = event.get('classification').get('classification')
            insurance_type = event.get('classification').get('insuranceType')
            print(f"Job ID: {job_id}")
            print(f"Document type: {document_type}")
            print(f"Insurance type: {insurance_type}")
                
            if not bucket or not key:
                raise ValueError("Missing S3 bucket or key in input event")

            print(f"Original encoded key: {encoded_key}")
            print(f"Decoded key for S3: {key}")
            print(f"Processing s3://{bucket}/{key} with document type: {document_type}")
            
            safe_filename = os.path.basename(key) 
            download_path = f'/tmp/{safe_filename}'
            print(f"Download path set to: {download_path}")


            # --- Update DynamoDB status to EXTRACTING ---
            if job_id and jobs_table_name:
                try:
                    timestamp_now = datetime.now(timezone.utc).isoformat()
                    dynamodb_client.update_item(
                        TableName=jobs_table_name,
                        Key={'jobId': {'S': job_id}},
                        UpdateExpression="SET #status_attr = :status_val, #extractStartTs = :extractStartTsVal",
                        ExpressionAttributeNames={
                            '#status_attr': 'status',
                            '#extractStartTs': 'extractionStartTimestamp'
                        },
                        ExpressionAttributeValues={
                            ':status_val': {'S': 'EXTRACTING'},
                            ':extractStartTsVal': {'S': timestamp_now}
                        }
                    )
                    print(f"Updated job {job_id} status to EXTRACTING")
                except Exception as ddb_e:
                    print(f"Error updating DynamoDB status for job {job_id}: {str(ddb_e)}")

        except (KeyError, ValueError, TypeError) as e:
            print(f"Error extracting input parameters: {e}")
            extraction_result["message"] = f"Error extracting input parameters: {str(e)}"
            return extraction_result
        print(f"Successfully extracted input parameters. Bucket: {bucket}, Key: {key}, DocType: {document_type}")

        # --- Step 2: Download PDF from S3 ---
        try:
            s3.download_file(bucket, key, download_path)
            print(f"Successfully downloaded to {download_path}")
        except Exception as e:
            print(f"Error downloading from S3: {e}")
            extraction_result["message"] = f"Error downloading from S3: {str(e)}"
            return extraction_result
        print(f"Successfully downloaded PDF from S3 to {download_path}")

        # --- Step 3: Convert PDF pages to images ---
        try:
           
            print(f"Attempting to convert PDF to images.")
            images = convert_from_path(download_path, dpi=200, fmt='JPEG', first_page=1)
            print(f"Successfully converted {len(images)} pages to images.")
            
            if not images:
                raise ValueError("No images were extracted from the PDF")
                
        except Exception as e:
            print(f"Error converting PDF to images: {e}")
            extraction_result["message"] = f"Error converting PDF to images: {str(e)}"
            return extraction_result
        
        # Prepare raw image bytes for Bedrock
        print(f"Starting image processing loop to convert to bytes.")
        image_byte_list = [] 
        for i, img in enumerate(images):
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG")
            raw_bytes = buffer.getvalue()
            image_byte_list.append(raw_bytes)
        print(f"Finished image processing loop. {len(image_byte_list)} images converted to bytes.")

        # --- Step 4 & 5: Batch process pages, create prompt, call Bedrock ---
        all_extracted_data = {}
        page_idx = 0
        total_pages = len(image_byte_list)
        insurance_type = event.get('classification', {}).get('insuranceType', 'property_casualty')

        while page_idx < total_pages:
            batch_images = image_byte_list[page_idx : page_idx + BATCH_SIZE]
            batch_page_nums = list(range(page_idx + 1, page_idx + 1 + len(batch_images)))
            
            print(f"Processing batch for pages: {batch_page_nums}")

            # Get the stateful extraction prompt
            previous_analysis_json = json.dumps(all_extracted_data, indent=2)
            prompt_text = get_extraction_prompt(document_type, insurance_type, batch_page_nums, previous_analysis_json)

            # Prepare the content for the user message in Converse API
            converse_user_message_content = [{"text": prompt_text}]
            for i, raw_image_data in enumerate(batch_images):
                page_number = batch_page_nums[i]
                # Adding a text marker for which page is which could be helpful for the model
                converse_user_message_content.append({"text": f"--- Image for Page {page_number} ---"})
                converse_user_message_content.append({
                    "image": {
                        "format": "jpeg",
                        "source": {"bytes": raw_image_data}
                    }
                })

            # Call Bedrock with Claude 3 using the Converse API
            try:
                model_id = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-sonnet-20240229-v1:0')
                
                print(f"Preparing to call Bedrock Converse API with model {model_id} for pages {batch_page_nums}.")
                response = bedrock_runtime.converse(
                    modelId=model_id,
                    messages=[{
                        "role": "user",
                        "content": converse_user_message_content
                    }],
                    inferenceConfig={
                        "maxTokens": 4096,
                        "temperature": 0.0
                    }
                )
                print(f"Received raw response from Bedrock Converse API for pages {batch_page_nums}.")
                
            except Exception as e:
                print(f"Error calling Bedrock for batch {batch_page_nums}: {e}")
                extraction_result["message"] = f"Error calling Bedrock: {str(e)}"
                return extraction_result

            # --- Step 6: Parse response and merge results ---
            output_message = response.get('output', {}).get('message', {})
            if not output_message or not output_message.get('content'):
                print(f"Bedrock response missing 'output' or 'content' field for batch {batch_page_nums}. Response: {json.dumps(response)}")
                page_idx += BATCH_SIZE
                continue
            
            assistant_response_text = output_message.get('content', [])[0]['text']
            print(f"Successfully extracted assistant response text. Length: {len(assistant_response_text)}")

            try:
                print(f"Attempting to parse JSON from Bedrock response...")
                json_str = assistant_response_text
                # Clean potential markdown ```json ... ```
                json_match = re.search(r'```json\s*([\s\S]*?)\s*```', assistant_response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    # Last resort: find anything that looks like a JSON object
                    json_match = re.search(r'(\{[\s\S]*\})', assistant_response_text, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                
                batch_data = json.loads(json_str)

                # --- Merge batch_data into all_extracted_data ---
                print("Merging batch data into overall results...")
                for doc_type, pages_list in batch_data.items():
                    if not isinstance(pages_list, list):
                        print(f"Warning: Value for key '{doc_type}' is not a list, skipping.")
                        continue

                    if doc_type in all_extracted_data:
                        all_extracted_data[doc_type].extend(pages_list)
                    else:
                        all_extracted_data[doc_type] = pages_list
                print("Merge complete for this batch.")

            except (json.JSONDecodeError, ValueError) as e:
                print(f"Error parsing JSON from response for batch {batch_page_nums}: {e}")
                print(f"Raw response was: {assistant_response_text}")
            
            # Move to the next batch
            page_idx += BATCH_SIZE

        print(f"All extracted data: {all_extracted_data}")

        # --- DynamoDB Update Logic --- 
        if job_id and jobs_table_name and all_extracted_data:
            try:
                timestamp_now = datetime.now(timezone.utc).isoformat()
                
                update_expression_parts = [
                    "SET #docType = :docType", 
                    "#extDataJsonStr = :extDataJsonStrVal", 
                    "#extTimestamp = :extTimestampVal"
                ]
                expression_attribute_names = {
                    '#docType': 'documentType',
                    '#extDataJsonStr': 'extractedDataJsonStr', 
                    '#extTimestamp': 'extractionTimestamp'
                }
                expression_attribute_values = {
                    ':docType': {'S': document_type},
                    ':extDataJsonStrVal': {'S': json.dumps(all_extracted_data)},
                    ':extTimestampVal': {'S': timestamp_now}
                }

                inferred_insurance_type = None
                if document_type in ["COMMERCIAL_PROPERTY_APPLICATION", "FINANCIAL_STATEMENT"]:
                    inferred_insurance_type = "property_casualty"
                elif document_type in ["MEDICAL_REPORT"]:
                    inferred_insurance_type = "life"
                
                if inferred_insurance_type:
                    update_expression_parts.append("#insType = :insTypeVal")
                    expression_attribute_names['#insType'] = 'insuranceType'
                    expression_attribute_values[':insTypeVal'] = {'S': inferred_insurance_type}

                dynamodb_client.update_item(
                    TableName=jobs_table_name,
                    Key={'jobId': {'S': job_id}},
                    UpdateExpression=', '.join(update_expression_parts),
                    ExpressionAttributeNames=expression_attribute_names,
                    ExpressionAttributeValues=expression_attribute_values
                )
                print(f"Successfully updated job {job_id} in DynamoDB with extraction results.")
            except Exception as ddb_e:
                print(f"Error updating DynamoDB for job {job_id}: {str(ddb_e)}. Proceeding without DDB update.")
        else:
            print("Skipping DynamoDB update: jobId not parsed, table name missing, or no extracted data.")

        # Return the extracted data
        extraction_result = {
            "status": "SUCCESS",
            "message": f"Successfully extracted data from {document_type}",
            "document_type": document_type,
            "data": all_extracted_data
        }

    finally:
        # Clean up temporary files
        if download_path and os.path.exists(download_path):
            try:
                os.remove(download_path)
                print(f"Cleaned up temporary file: {download_path}")
            except Exception as e:
                print(f"Error during cleanup: {e}")

    print(f"Final extraction result: {json.dumps(extraction_result)}")
    return extraction_result