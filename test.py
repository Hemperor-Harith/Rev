from flask import Flask, request, jsonify
import requests
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from flask_cors import CORS

load_dotenv()

app = Flask(__name__)
CORS(app)

def clean(val):
    if not val:
        return ''
    return str(val).replace('\n', ' ').replace('\r', ' ').strip()

def format_plan_for_email(plan_json, student_name):
    try:
        output = f"Hi {student_name}! Here is your personalised revision plan:\n\n"
        output += "=" * 50 + "\n\n"
        for day in plan_json.get("plan", []):
            output += f"📅 {day['day'].upper()} {day['date']}\n"
            if day.get("rest_day"):
                output += "🌟 REST DAY — No revision today. Rest is part of the plan.\n\n"
                continue
            output += f"Total revision time: {day['total_mins']} mins\n\n"
            for i, session in enumerate(day.get("sessions", []), 1):
                output += f"SESSION {i} — {session['subject']} — {session['duration_mins']} mins\n"
                output += f"📖 Topic: {session['topic']}\n"
                output += f"🛠 Technique: {session['technique']}\n"
                output += f"📝 Instructions: {session['instructions']}\n"
                output += f"💡 Why this works for you: {session['why_it_works']}\n\n"
            output += f"✨ {day['encouragement']}\n"
            output += "-" * 50 + "\n\n"
        return output
    except Exception as e:
        return f"Plan generated but formatting failed: {e}\n\nRaw data: {json.dumps(plan_json)}"

def send_email(to_email, student_name, plan_text):
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {os.getenv('RESEND_API_KEY')}",
            "Content-Type": "application/json"
        },
        json={
            "from": "PlanMyRevision <onboarding@resend.dev>",
            "to": [to_email],
            "subject": f"📚 Your Personalised Revision Plan, {student_name}!",
            "text": plan_text
        }
    )
    return response.status_code == 200

def save_to_sheet(student_name, email, reminders, plan_text):
    sheet_url = os.getenv('SHEET_WEBHOOK_URL', '')
    if not sheet_url:
        return
    try:
        requests.post(sheet_url, json={
            "name": student_name, "email": email,
            "reminders": reminders, "plan": plan_text,
            "date": datetime.now().strftime("%Y-%m-%d")
        }, timeout=5)
    except Exception:
        pass

@app.route('/generate-plan', methods=['POST'])
def generate_plan():
    data = request.json
    today = datetime.now()
    today_str = today.strftime("%A %d %B %Y")
    subjects_raw = clean(data.get('subjects', ''))
    student_name = clean(data.get('name', 'Student'))
    student_email = clean(data.get('email', ''))
    reminders = clean(data.get('reminders', 'no'))

    with open("prompt.txt", "r") as f:
        base_prompt = f.read()

    full_prompt = f"""{base_prompt}

TODAY'S DATE AND TIME CONTEXT:
- Today is {today_str}
- Use this to calculate exactly how many days remain until each exam
- Calculate which days of the week fall on which dates yourself
- Never revise on: {clean(data.get('unavailable_days', 'None'))}
- Stop the revision plan the day before exams begin
- In the final 3 days before each exam, only revise that subject lightly

STUDENT PROFILE:
- Name: {student_name}
- Year: {clean(data.get('year', 'Year 10'))}
- Exams begin: {clean(data.get('exam_start', 'Unknown'))}
- Daily time available: {clean(data.get('daily_hours', '1-2 hours'))}
- Session preference: {clean(data.get('session_style', 'Mixed'))}
- Reminders: {reminders}

SUBJECTS, CONFIDENCE RATINGS AND EXAM DATES:
{subjects_raw}

ADDITIONAL CONTEXT:
- Distractions: {clean(data.get('distractions', 'Various'))}
- Sleep: {clean(data.get('sleep', 'Unknown'))}
- Prior techniques: {clean(data.get('prior_techniques', 'None'))}
- Additional notes: {clean(data.get('notes', 'None'))}

SCHEDULING RULES:
- Calculate exact days remaining until each exam from today
- Prioritise low confidence subjects with early exam dates most urgently
- Sessions must never exceed 45 minutes each
- Maximum 90 minutes total revision per day
- Never same subject on consecutive days unless it is the weakest subject in week one
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
    raw_content = result["choices"][0]["message"]["content"]

    # Clean up markdown code blocks if present
    clean_content = raw_content.strip()
    if "```" in clean_content:
        parts = clean_content.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                clean_content = part
                break

    clean_content = clean_content.strip()

    # Try to parse as JSON and format nicely
    formatted_plan = None
    plan_store = raw_content

    try:
        plan_json = json.loads(clean_content)
        formatted_plan = format_plan_for_email(plan_json, student_name)
        plan_store = json.dumps(plan_json)
    except Exception:
        # JSON parsing failed - send raw content but clean it up a bit
        formatted_plan = raw_content

    # Send email
    if student_email and formatted_plan:
        send_email(student_email, student_name, formatted_plan)

    save_to_sheet(student_name, student_email, reminders, plan_store)

    return jsonify({
        "status": "success",
        "plan": formatted_plan,
        "plan_json": plan_store,
        "student_name": student_name,
        "student_email": student_email
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "running"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
