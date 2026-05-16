from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

@app.route('/generate-plan', methods=['POST'])
def generate_plan():
    data = request.json
    
    today = datetime.now()
    today_str = today.strftime("%A %d %B %Y")
    
    # Build subject list from form data
    subjects_raw = data.get('subjects', '')
    confidence_raw = data.get('confidence', '')
    exam_dates_raw = data.get('exam_dates', '')
    
    with open("prompt.txt", "r") as f:
        base_prompt = f.read()
    
    full_prompt = f"""{base_prompt}

TODAY'S DATE AND TIME CONTEXT:
- Today is {today_str}
- Use this to calculate exactly how many days remain until each exam
- Calculate which days of the week fall on which dates yourself
- Never revise on: {data.get('unavailable_days', 'Wednesday')}
- Stop the revision plan the day before exams begin
- In the final 3 days before each exam, only revise that subject lightly

STUDENT PROFILE:
- Name: {data.get('name', 'Student')}
- Year: {data.get('year', 'Year 10')}
- Exams begin: {data.get('exam_start', 'Unknown')}
- Daily time available: {data.get('daily_hours', '1-2 hours')}
- Session preference: {data.get('session_style', 'Mixed')}

SUBJECTS AND CONFIDENCE:
{subjects_raw}

CONFIDENCE RATINGS:
{confidence_raw}

EXAM DATES PER SUBJECT:
{exam_dates_raw}

ADDITIONAL CONTEXT:
- Distractions: {data.get('distractions', 'Various')}
- Sleep: {data.get('sleep', 'Unknown')}
- Prior techniques: {data.get('prior_techniques', 'None')}
- Additional notes: {data.get('notes', 'None')}

SCHEDULING RULES:
- Calculate exact days remaining until each exam from today
- Prioritise low confidence subjects with early exam dates most urgently
- Sessions must never exceed 45 minutes each
- Maximum 90 minutes total revision per day
- Never same subject on consecutive days unless Chinese in week one
- Day before each exam: only that subject, light recall, finish by 7pm
- Exam morning: 15 minute confidence session only
"""

    response = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            "Content-Type": "application/json"
        },
        json={
            "model": "anthropic/claude-3-haiku",
            "messages": [
                {"role": "system", "content": full_prompt},
                {"role": "user", "content": "Please generate my personalised revision plan."}
            ],
            "max_tokens": 8000
        }
    )

    result = response.json()
    plan = result["choices"][0]["message"]["content"]
    
    return jsonify({
        "status": "success",
        "plan": plan,
        "student_name": data.get('name', 'Student'),
        "student_email": data.get('email', '')
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "running"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)