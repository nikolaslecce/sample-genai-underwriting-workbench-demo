import json
import boto3
import os
import io
import urllib.parse
import re
import gc
from datetime import datetime, timezone
from pdf2image import pdfinfo_from_path, convert_from_path
from PIL import Image, ImageOps
# Initialize AWS clients outside the handler for reuse
s3 = boto3.client('s3')
bedrock = boto3.client(service_name='bedrock-runtime')
dynamodb = boto3.client('dynamodb')
JOBS_TABLE = os.environ.get('JOBS_TABLE_NAME')
BATCH_SIZE = 1
DPI = 150
MAX_DIMENSION = 8000

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
    batch_data = {}        # make sure this exists no matter what
    # --- 1) Parse event ---
    try:
        bucket = event['detail']['bucket']['name']
        key = urllib.parse.unquote_plus(event['detail']['object']['key'])
        job_id = event['classification']['jobId']
        doc_type = event['classification']['classification']
        ins_type = event['classification']['insuranceType']
    except Exception as e:
        return {"status": "ERROR", "message": f"Invalid event format: {e}"}

    # --- 2) Mark EXTRACTING in DynamoDB ---
    if job_id and JOBS_TABLE:
        try:
            now = datetime.now(timezone.utc).isoformat()
            dynamodb.update_item(
                TableName=JOBS_TABLE,
                Key={'jobId': {'S': job_id}},
                UpdateExpression="SET #s = :s, #t = :t",
                ExpressionAttributeNames={'#s': 'status', '#t': 'extractionStartTimestamp'},
                ExpressionAttributeValues={':s': {'S': 'EXTRACTING'}, ':t': {'S': now}},
            )
        except Exception:
            pass

    # --- 3) Download PDF locally ---
    local_path = f"/tmp/{os.path.basename(key)}"
    try:
        s3.download_file(bucket, key, local_path)
    except Exception as e:
        return {"status": "ERROR", "message": f"S3 download failed: {e}"}

    # --- 4) Read total pages from PDF ---
    try:
        info = pdfinfo_from_path(local_path)
        total_pages_full = int(info.get("Pages", 0))
    except Exception as e:
        return {"status": "ERROR", "message": f"Could not read PDF info: {e}"}

    # --- 5) Determine page batches (or single range) ---
    page_range = event.get('pages')
    page_batches = []
    if page_range:
        # single batch from SF Map
        first_page = page_range.get('start', 1)
        last_page = page_range.get('end', first_page)
        page_batches.append((first_page, last_page))
    else:
        # full-document batching
        page = 1
        while page <= total_pages_full:
            last = min(page + BATCH_SIZE - 1, total_pages_full)
            page_batches.append((page, last))
            page = last + 1

    all_data = {}

    # --- 6) Process each batch in sequence (Step Functions will parallelize via Map) ---
    for (first, last) in page_batches:
        # Convert only this batch to images
        try:
            imgs = convert_from_path(
                local_path,
                dpi=DPI,
                fmt='JPEG',
                first_page=first,
                last_page=last
            )
        except Exception as e:
            return {"status": "ERROR", "message": f"PDF→image conversion failed for pages {first}–{last}: {e}"}

        # Build prompt & payload
        prompt = get_extraction_prompt(doc_type, ins_type, list(range(first, last+1)), json.dumps(all_data, indent=2))
        messages = [{"text": prompt}]
        for idx, img in enumerate(imgs, start=first):
            img = img.convert("L")
            img = ImageOps.crop(img, border=50)
            w, h = img.size
            if max(w, h) > MAX_DIMENSION:
                scale = MAX_DIMENSION / float(max(w, h))
                img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=60, optimize=True)
            payload_bytes = buf.getvalue()
            buf.close()
            messages.append({"text": f"--- Image for Page {idx} ---"})
            messages.append({"image": {"format": "jpeg", "source": {"bytes": payload_bytes}}})

        # Call Bedrock Converse API
        try:
            resp = bedrock.converse(
                modelId=os.environ.get('BEDROCK_MODEL_ID'),
                messages=[{"role": "user", "content": messages}],
                inferenceConfig={"maxTokens": 4096, "temperature": 0.0}
            )
        except Exception as e:
            return {"status": "ERROR", "message": f"Bedrock call failed for pages {first}–{last}: {e}"}

        # Extract JSON
        output = resp.get('output', {}).get('message', {})
        text = (output.get('content') or [{}])[0].get('text', '')
        match = (re.search(r'```json\s*([\s\S]*?)```', text, re.DOTALL)
                 or re.search(r'(\{[\s\S]*\})', text, re.DOTALL))
        if match:
            try:
                batch_data = json.loads(match.group(1))
                for k, pages_list in batch_data.items():
                    all_data.setdefault(k, []).extend(pages_list or [])
            except Exception:
                pass

        # Cleanup
        del imgs
        gc.collect()

    # --- 8) Cleanup & return ---
    try:
        os.remove(local_path)
    except OSError:
        pass

    chunk_key = f"{job_id}/extracted/{first_page}-{last_page}.json"
    s3.put_object(
    Bucket=os.environ['EXTRACTION_BUCKET'],
    Key=chunk_key,
    Body=json.dumps(batch_data),
    )
    return {
    "pages": {"start": first_page, "end": last_page},
    "chunkS3Key": chunk_key
    }