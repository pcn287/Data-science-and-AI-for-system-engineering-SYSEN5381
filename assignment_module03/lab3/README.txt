Lab 3: AI-Powered Data Reporter
==============================

Script: AI-powered reporter.py
Generated report: emissions_report.html

Brief explanation of development:
--------------------------------

1. Initially, the report was generated without AI. The script used a fixed HTML template and rule-based logic (pandas aggregation, sorting) to build the emissions report. The HTML was constructed from f-strings and predefined structure.

2. Later, AI was included. The script was updated to use the OpenAI API (gpt-4o-mini model). The AI is invoked in the generate_report_with_openai() function, which:
   - Sends the raw C-Lock emissions CSV data to the OpenAI Chat Completions API
   - Uses a system prompt instructing the model to act as a data analyst
   - Asks the model to analyze the data, summarize key findings (trends, top/low emitters, statistics), and produce a complete HTML report
   - Receives the generated HTML from the model and saves it to emissions_report.html

3. The AI now performs both the data analysis and the report generation. The script loads OPENAI_API_KEY from the .env file to authenticate with OpenAI.
