import React, { useEffect } from 'react';
import '../styles/HowItWorksDrawer.css'



interface HowItWorksDrawerProps {
  onClose: () => void;
}

export const HowItWorksDrawer: React.FC<HowItWorksDrawerProps> = ({ onClose }) => {
  // Keep the page analysis and underwriting prompt handlers for reference in the prompt examples
  const showPageAnalysisPrompt = () => {
    alert(`Page Analysis Prompt:
----------------------------
You are an underwriter analyzing pages from a pdf containing an individual life insurance application.
Your job is to extract all relevant data from each page related to life insurance underwriting, such as:
- Health details (medical history, conditions, medications, lab results)
- Occupation information
- Credit scores
- Driving history
- Hobbies
- Discrepancies (contradictory or unclear information)

Guidelines:
- For each page, think about the page in <thinking>...</thinking> tags. 
- Then Output your the page details in <output page="X">...</output> tags. 
- Within the <output>, start with a description of the <page_type>, such as "Pharmacy Report" or "Driving History" or "Occupation History"
   - If it's a continuation of a previous page, add "-Continued"
- Then include all information relevant to life insurance underwriting in <page_content>...</page_content> tags. Dates are very important.  
- Do not mention absent information, as each page will pertain to only specific information.`);
  };

  const showUnderwritingPrompt = () => {
    alert(`Underwriting Analysis Prompt:
----------------------------
You are a senior life insurance underwriter. I will show you page-level summaries from an underwriting document. Your job: combine them into an overall risk assessment. Identify specific risks, callouts, and discrepancies.

You must:
1) Keep a chain-of-thought in <thinking>...</thinking> tags. Write 10-15 paragraphs summarizing your thoughts.
2) Produce interim and final results in <output> tags containing VALID JSON like this exact format:
3) Cite the page number(s) where info was found. Keep updating and refining your assessment each time you receive new page summaries.

The JSON output must follow this structure:
{
    "RISK_ASSESSMENT": "Detailed assessment with page references...",
    "DISCREPANCIES": "List of any conflicting information found with page references (pay special attention to medication prescriptions, which can indicate undisclosed conditions)",
    "MEDICAL_TIMELINE": "Timeline of major medical events ordered by date with page references. Only include major medical events, not minor ones.",
    "FINAL_RECOMMENDATION": "Clear recommendation based on all data. Do not make recommendations on accept or decline, but rather observe risks and recommend next steps."
}

Important:
- Use EXACTLY the aforementioned key names
- Make sure your JSON is properly formatted with quotes
- Include page numbers in your analysis
- Put the entire JSON inside <output> tags

Guidelines:
- Always include the page number(s) in your analysis. Use exactly this format "(pg 1)", "(pg 1, pg 7)"
- Your general rule of thumb should be to add or refine information to the JSON, but not remove information.
- Avoid speculative or subjective language such as "unrealistic." Instead, note any concerns or red flags factually and request clarification if needed.
- Avoid strong or overly aggressive or conclusive language like "clear pattern of material misrepresentation".
- Refrain from definitive conclusions about undisclosed or ongoing conditions unless explicitly supported by the source text. If something is uncertain, mark it as "requires further clarification" or "possible discrepancy."
- Generally you should aim to describe the page in a way that is useful for an underwriter to make a decision, but not make judgement calls (except for the FINAL_RECOMMENDATION)`);
  };

  // Add window functions for the prompts (kept for reference in examples)
  useEffect(() => {
    (window as any).showPageAnalysisPrompt = showPageAnalysisPrompt;
    (window as any).showUnderwritingPrompt = showUnderwritingPrompt;

    return () => {
      delete (window as any).showPageAnalysisPrompt;
      delete (window as any).showUnderwritingPrompt;
    };
  }, []);

  return (
    <div className="how-it-works-drawer">
      <button className="drawer-close" onClick={onClose}>Close</button>
      <div className="drawer-content">
        <h2>How It Works</h2>
        
        <section className="flow-overview">
          <h3>Document Analysis Flow</h3>
          <p>This application processes insurance documents through a sophisticated AI-powered pipeline. Here's how it works:</p>
        </section>

        {/* Flow diagram image */}
        <div className="flow-diagram">
          <img 
            src="/flow.png" 
            alt="Document Analysis Workflow" 
            style={{ width: '100%', maxWidth: '100%', margin: '20px 0' }}
          />
        </div>

        <section className="flow-details">
          <h3>Step-by-Step Process</h3>
          
          <div className="step">
            <h4>1. Document Upload</h4>
            <p>When you upload a PDF document, the system securely stores it and initiates the analysis process.</p>
          </div>

          <div className="step">
            <h4>2. PDF to Image Conversion</h4>
            <p>The PDF is converted to images to prepare for AI processing.</p>
          </div>

          <div className="step">
            <h4>3. Page Chunking</h4>
            <p>Documents are divided into batches of N pages to optimize processing efficiency.</p>
          </div>

          <div className="step">
            <h4>4. Process Batch With Claude Sonnet</h4>
            <p>Each batch of pages is analyzed by Claude Sonnet to extract relevant underwriting information:</p>
            <ul>
              <li>Each page's content is extracted and categorized (e.g., "Pharmacy Report", "Driving History")</li>
              <li>Relevant underwriting information is structured for storage</li>
            </ul>
          </div>

          <div className="step">
            <h4>5. Store Page Analysis in DynamoDB</h4>
            <p>Page-level analysis results are stored in DynamoDB for persistence and future retrieval.</p>
          </div>

          <div className="step">
            <h4>6. Process Additional Pages</h4>
            <p>The system checks if more pages need processing:</p>
            <ul>
              <li>If yes: Continue processing the next batch of pages</li>
              <li>If no: Proceed to aggregate the analysis results</li>
            </ul>
          </div>

          <div className="step">
            <h4>7. Aggregate Page Summaries</h4>
            <p>All page-level analyses are combined to prepare for comprehensive underwriting analysis.</p>
          </div>

          <div className="step">
            <h4>8. Underwriting Analysis With Claude Sonnet</h4>
            <p>A comprehensive underwriting analysis is performed:</p>
            <ul>
              <li>The AI model acts as a senior underwriter, reviewing all page summaries</li>
              <li>Information is synthesized into a structured risk assessment</li>
              <li>The analysis includes:
                <ul>
                  <li>Overall risk assessment with page references</li>
                  <li>Identification of discrepancies or unclear information</li>
                  <li>Timeline of major medical events</li>
                  <li>Final recommendations for next steps</li>
                </ul>
              </li>
            </ul>
          </div>

          <div className="step">
            <h4>9. Store Final Analysis in DynamoDB</h4>
            <p>The complete underwriting analysis is stored in DynamoDB for persistence and retrieval.</p>
          </div>

          <div className="step">
            <h4>10. Analysis Complete, Notify User</h4>
            <p>The user is notified that the analysis is complete and ready for review.</p>
          </div>
        </section>

        <section className="prompt-examples">
          <h3>AI Prompts</h3>
          <p>The system uses two specialized prompts to guide the AI analysis process:</p>
          
          <h4>1. Page Analysis Prompt</h4>
          <p>Used to analyze individual pages and extract structured information:</p>
          <pre>{`You are an underwriter analyzing pages from a pdf containing an individual life insurance application.
Your job is to extract all relevant data from each page related to life insurance underwriting, such as:
- Health details (medical history, conditions, medications, lab results)
- Occupation information
- Credit scores
- Driving history
- Hobbies
- Discrepancies (contradictory or unclear information)

Guidelines:
- For each page, think about the page in <thinking>...</thinking> tags. 
- Then Output your the page details in <output page="X">...</output> tags. 
- Within the <output>, start with a description of the <page_type>, such as "Pharmacy Report" or "Driving History" or "Occupation History"
   - If it's a continuation of a previous page, add "-Continued"
- Then include all information relevant to life insurance underwriting in <page_content>...</page_content> tags. Dates are very important.  
- Do not mention absent information, as each page will pertain to only specific information.`}</pre>

          <h4>2. Underwriting Analysis Prompt</h4>
          <p>Used to synthesize page summaries into a comprehensive risk assessment:</p>
          <pre>{`You are a senior life insurance underwriter. I will show you page-level summaries from an underwriting document. Your job: combine them into an overall risk assessment. Identify specific risks, callouts, and discrepancies.

You must:
1) Keep a chain-of-thought in <thinking>...</thinking> tags. Write 10-15 paragraphs summarizing your thoughts.
2) Produce interim and final results in <output> tags containing VALID JSON like this exact format:
3) Cite the page number(s) where info was found. Keep updating and refining your assessment each time you receive new page summaries.

The JSON output must follow this structure:
{
    "RISK_ASSESSMENT": "Detailed assessment with page references...",
    "DISCREPANCIES": "List of any conflicting information found with page references (pay special attention to medication prescriptions, which can indicate undisclosed conditions)",
    "MEDICAL_TIMELINE": "Timeline of major medical events ordered by date with page references. Only include major medical events, not minor ones.",
    "FINAL_RECOMMENDATION": "Clear recommendation based on all data. Do not make recommendations on accept or decline, but rather observe risks and recommend next steps."
}

Important:
- Use EXACTLY the aforementioned key names
- Make sure your JSON is properly formatted with quotes
- Include page numbers in your analysis
- Put the entire JSON inside <output> tags

Guidelines:
- Always include the page number(s) in your analysis. Use exactly this format "(pg 1)", "(pg 1, pg 7)"
- Your general rule of thumb should be to add or refine information to the JSON, but not remove information.
- Avoid speculative or subjective language such as "unrealistic." Instead, note any concerns or red flags factually and request clarification if needed.
- Avoid strong or overly aggressive or conclusive language like "clear pattern of material misrepresentation".
- Refrain from definitive conclusions about undisclosed or ongoing conditions unless explicitly supported by the source text. If something is uncertain, mark it as "requires further clarification" or "possible discrepancy."
- Generally you should aim to describe the page in a way that is useful for an underwriter to make a decision, but not make judgement calls (except for the FINAL_RECOMMENDATION)`}</pre>
        </section>
      </div>
    </div>
  );
}; 