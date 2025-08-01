import json
import boto3
import os
import re
from datetime import datetime, timezone # ADDED

# Initialize AWS clients outside the handler for reuse
bedrock_runtime = boto3.client(service_name='bedrock-runtime')
dynamodb_client = boto3.client('dynamodb') # ADDED
jobs_table_name_env = os.environ.get('JOBS_TABLE_NAME') # ADDED

# Define the expected output schema for this analysis lambda
ANALYSIS_OUTPUT_SCHEMA = {
    "overall_summary": "string",
    "identified_risks": [
        {"risk_description": "string", "severity": "string", "page_references": ["string"]}
    ],
    "discrepancies": [
        {"discrepancy_description": "string", "details": "string", "page_references": ["string"]}
    ],
    "medical_timeline": "string", # Markdown text for UI
    "property_assessment": "string", # Markdown text for UI
    "final_recommendation": "string", # Markdown text for UI
    "missing_information": [
        {"item_description": "string", "notes": "string"}
    ],
    "confidence_score": "float" 
}

def validate_analysis_data(data, schema):
    """
    Validates the structure of the data against the schema.
    Checks for presence of top-level keys and basic structure of nested lists/dicts.
    Args:
        data (dict): The data to validate.
        schema (dict): The schema to validate against.
    Returns:
        bool: True if validation passes basic checks, False otherwise.
    """
    is_valid = True
    if not isinstance(data, dict):
        print("Validation Error: Overall data is not a dictionary.")
        return False

    for key, schema_value_type in schema.items():
        if key not in data:
            print(f"Validation Warning: Missing top-level key '{key}' in extracted data.")
            # Add missing key with default to allow processing
            data[key] = [] if isinstance(schema_value_type, list) else {} if isinstance(schema_value_type, dict) else "N/A" 
            is_valid = False
            continue 

        # Basic type checking for lists (like identified_risks)
        if isinstance(schema_value_type, list) and isinstance(schema_value_type[0], dict):
            if not isinstance(data[key], list):
                print(f"Validation Error: Key '{key}' should be a list, but found {type(data[key])}.")
                is_valid = False
                continue
    
    return is_valid

def lambda_handler(event, context):
    print("Received event:", json.dumps(event))
    
    # Initialize variables
    extracted_data = None
    analysis_output = {"status": "ERROR", "message": "Processing not completed", "analysis_data": {}}
    job_id = None 
    
    try:
        # --- Step 1: Extract Input Parameters and Load Data ---
        try:
            # The Step Function passes the entire output from the previous step
            if 'extraction' not in event or not isinstance(event['extraction'], dict):
                raise ValueError("Missing or invalid 'extraction' field in input event")

            extraction_result = event['extraction']

            if extraction_result.get('status') != 'SUCCESS':
                raise ValueError(f"Previous extraction step failed: {extraction_result.get('message', 'Unknown error')}")

            extracted_data = extraction_result.get('data')
            job_id = event.get('classification').get('jobId')
            insurance_type = event.get('classification').get('insuranceType')
            document_type = event.get('classification').get('classification')
            print(f"Job ID: {job_id}")
            print(f"Document type: {document_type}")
            print(f"Insurance type: {insurance_type}")

            if not document_type or not extracted_data:
                raise ValueError("Missing 'document_type' or 'data' in extraction result")
            if not job_id: # ADDED: Check for jobId
                print("Warning: Missing 'jobId' in extraction result. DynamoDB update will be skipped.")

            # --- Update DynamoDB status to ANALYZING ---
            if job_id and jobs_table_name_env:
                try:
                    timestamp_now = datetime.now(timezone.utc).isoformat()
                    dynamodb_client.update_item(
                        TableName=jobs_table_name_env,
                        Key={'jobId': {'S': job_id}},
                        UpdateExpression="SET #status_attr = :status_val, #analyzeStartTs = :analyzeStartTsVal",
                        ExpressionAttributeNames={
                            '#status_attr': 'status',
                            '#analyzeStartTs': 'analysisStartTimestamp'
                        },
                        ExpressionAttributeValues={
                            ':status_val': {'S': 'ANALYZING'},
                            ':analyzeStartTsVal': {'S': timestamp_now}
                        }
                    )
                    print(f"Updated job {job_id} status to ANALYZING")
                except Exception as ddb_e:
                    print(f"Error updating DynamoDB status for job {job_id}: {str(ddb_e)}")

            print(f"Successfully loaded extracted data for document type: {document_type}. Job ID: {job_id}")

        except (KeyError, ValueError, TypeError) as e:
            print(f"Error processing input event: {e}")
            analysis_output["message"] = f"Error processing input event: {str(e)}"
            return analysis_output

        # Prepare consolidated data for analysis
        print("Preparing consolidated data for prompt...")
        consolidated_text_for_analysis = json.dumps(extracted_data, indent=2)
        print(f"Consolidated data prepared. Length: {len(consolidated_text_for_analysis)} characters.")

        # --- Step 2: Construct Analysis Prompt ---
        print("Constructing analysis prompt...")
        analysis_prompt_text = f"""You are an expert insurance underwriter tasked with analyzing extracted document information.
        The following data was extracted from an insurance document:
        <extracted_data>
        {consolidated_text_for_analysis}
        </extracted_data>

        Please perform a comprehensive analysis. Your goal is to:
        1. Provide an 'overall_summary' of the document content and its purpose based on the extracted data.
        2. Identify key risks in 'identified_risks'. For each risk, include 'risk_description', 'severity' (Low, Medium, or High), and 'page_references' (list of strings, e.g., ["1", "3-5"], use ["N/A"] if not applicable).
        3. Identify any discrepancies or inconsistencies in 'discrepancies'. For each, include 'discrepancy_description', 'details' (provide specific details of the discrepancy), and 'page_references' (list of strings, e.g., ["2", "10"], use ["N/A"] if not applicable).
        4. Provide a 'medical_timeline' (string, use Markdown for formatting) if the document is medical-related. If not applicable, provide an empty string or "N/A".
        5. Provide a 'property_assessment' (string, use Markdown for formatting) if the document is property-related (e.g., commercial property application). If not applicable, provide an empty string or "N/A".
        6. Formulate a 'final_recommendation' (string, use Markdown for formatting) for the underwriter based on your analysis (e.g., approve, decline with reasons, request more info).
        7. List any critical missing information in 'missing_information'. For each, include 'item_description' and 'notes'.
        8. If you can estimate a 'confidence_score' (0.0 to 1.0) for your overall analysis based on the quality and completeness of the provided extracted data, include it. Otherwise, you can omit it or use a default like 0.75.
        
        Structure your response as a single JSON object matching the following schema precisely. Do not include any explanations or text outside this JSON structure:
        {json.dumps(ANALYSIS_OUTPUT_SCHEMA, indent=2)}
        
        Important Guidelines:
        - Adhere strictly to the JSON schema provided for the output.
        - If a section like 'identified_risks', 'discrepancies', or 'missing_information' has no items, provide an empty list ([]) for that key.
        - For 'page_references', if the source extracted data does not contain explicit page numbers associated with the information, use ["N/A"].
        - If you can estimate a 'confidence_score' (0.0 to 1.0) for your overall analysis based on the quality and completeness of the provided extracted data, include it. Otherwise, you can omit it or use a default like 0.75.
        
        Return ONLY the JSON object.
        """
        print(f"Analysis prompt created. Length: {len(analysis_prompt_text)} characters.")

        # --- Step 3: Call Bedrock for Analysis ---
        print("Calling Bedrock Converse API...")
        model_id = os.environ.get('BEDROCK_ANALYSIS_MODEL_ID', 'us.anthropic.claude-3-7-sonnet-20250219-v1:0') 
        
        converse_messages = [
            {
                "role": "user",
                "content": [{"text": analysis_prompt_text}]
            }
        ]
        
        try:
            response = bedrock_runtime.converse(
                modelId=model_id,
                messages=converse_messages,
                inferenceConfig={
                    "maxTokens": 4096, 
                    "temperature": 0.05  
                }
            )
            print("Received response from Bedrock.")
        except Exception as e:
            print(f"Error calling Bedrock Converse API: {e}")
            analysis_output["message"] = f"Error calling Bedrock: {str(e)}"
            return analysis_output

        # --- Step 4: Process and Validate Response ---
        print("Parsing and validating Bedrock response...")
        output_message = response.get('output', {}).get('message', {})
        if not output_message:
            raise ValueError("Bedrock Converse API response missing 'output' or 'message' field.")

        assistant_response_content_list = output_message.get('content', [])
        if not assistant_response_content_list or \
        not isinstance(assistant_response_content_list[0], dict) or \
        'text' not in assistant_response_content_list[0]:
            raise ValueError("Bedrock Converse API response content is not in the expected format or is empty.")
            
        assistant_response_text = assistant_response_content_list[0]['text']
        print(f"Extracted assistant response text. Length: {len(assistant_response_text)}")

        # Attempt to parse JSON robustly
        parsed_analysis_data = None
        try:
            parsed_analysis_data = json.loads(assistant_response_text) 
        except json.JSONDecodeError:
            print("Direct JSON parsing failed. Attempting to find JSON block using regex...")
            match = re.search(r'\{(?:[^{}]|\{[^{}]*\})*\}', assistant_response_text) 
            if match:
                json_block = match.group(0)
                print(f"Found potential JSON block: {json_block[:200]}...")
                try:
                    parsed_analysis_data = json.loads(json_block)
                except json.JSONDecodeError as e_inner:
                    print(f"Error parsing extracted JSON block: {e_inner}")
                    analysis_output["message"] = f"Could not parse JSON from Bedrock response: {str(e_inner)}"
                    return analysis_output 
            else:
                print(f"No JSON block found in response: {assistant_response_text}")
                analysis_output["message"] = "No valid JSON block found in Bedrock response."
                return analysis_output 
        
        if parsed_analysis_data is None:
            print(f"Error: Failed to parse JSON data from response text: {assistant_response_text}")
            analysis_output["message"] = "Failed to parse JSON data from Bedrock response."
            return analysis_output

        # Validate the structure of the parsed data
        print(f"Validating parsed data against schema...")
        if not validate_analysis_data(parsed_analysis_data, ANALYSIS_OUTPUT_SCHEMA):
            print("Warning: Parsed data structure validation failed or had warnings.")
            analysis_output["message"] = "Analysis completed, but output schema validation had warnings."
        else: 
            print("Parsed data structure validation successful.")
            analysis_output["message"] = "Analysis completed successfully."

        analysis_output["analysis_data"] = parsed_analysis_data
        analysis_output["status"] = "SUCCESS"
        analysis_output["insurance_type"] = insurance_type
        print("Successfully processed and validated analysis data.")

        # --- Step 5: Update DynamoDB --- ADDED BLOCK
        if job_id and jobs_table_name_env and parsed_analysis_data:
            try:
                timestamp_now = datetime.now(timezone.utc).isoformat()
                dynamodb_client.update_item(
                    TableName=jobs_table_name_env,
                    Key={'jobId': {'S': job_id}},
                    UpdateExpression="SET #analysisOutput = :analysisOutputVal, #analysisTs = :analysisTsVal",
                    ExpressionAttributeNames={
                        '#analysisOutput': 'analysisOutputJsonStr', # New DDB attribute
                        '#analysisTs': 'analysisTimestamp' # New DDB attribute
                    },
                    ExpressionAttributeValues={
                        ':analysisOutputVal': {'S': json.dumps(parsed_analysis_data)},
                        ':analysisTsVal': {'S': timestamp_now}
                    }
                )
                print(f"Successfully updated job {job_id} in DynamoDB with analysis results.")
            except Exception as ddb_e:
                print(f"Error updating DynamoDB for job {job_id} with analysis results: {str(ddb_e)}. Analysis data not saved to DDB.")
        elif not job_id:
            print("Skipping DynamoDB update for analysis results: job_id is missing.")
        # --- END OF DDB UPDATE BLOCK ---

    except Exception as e:
        print(f"Unhandled error in analyze-lambda: {e}")
        analysis_output["message"] = f"Unhandled error: {str(e)}"
            
    finally:
        pass

    print("Returning final analysis result:", json.dumps(analysis_output))
    return analysis_output