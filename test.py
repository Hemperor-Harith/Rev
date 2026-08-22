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

# ---------- HTML EMAIL BUILDERS ----------

EMAIL_STYLE = """
<style>
  body { font-family: Arial, Helvetica, sans-serif; background:#f4f6f8; margin:0; padding:0; color:#1f2937; }
  .container { max-width:600px; margin:0 auto; padding:24px 16px; }
  .header { background:#4f46e5; color:#ffffff; padding:20px 24px; border-radius:12px 12px 0 0; }
  .header h1 { margin:0; font-size:20px; }
  .card { background:#ffffff; border:1px solid #e5e7eb; border-top:none; border-radius:0 0 12px 12px; padding:20px 24px; }
  .day-block { margin-bottom:24px; padding-bottom:20px; border-bottom:1px solid #eef0f2; }
  .day-block:last-child { border-bottom:none; margin-bottom:0; padding-bottom:0; }
  .day-title { font-size:16px; font-weight:bold; color:#4f46e5; margin-bottom:4px; }
  .day-meta { font-size:13px; color:#6b7280; margin-bottom:12px; }
  .rest-banner { background:#ecfdf5; color:#065f46; padding:10px 14px; border-radius:8px; font-size:14px; }
  .session { background:#f9fafb; border-left:4px solid #4f46e5; border-radius:6px; padding:12px 14px; margin-bottom:10px; }
  .session-title { font-weight:bold; font-size:14px; margin-bottom:6px; }
  .session-row { font-size:13px; margin:3px 0; line-height:1.4; }
  .session-label { font-weight:bold; }
  .encouragement { font-size:14px; font-style:italic; color:#374151; margin-top:10px; }
  .footer { text-align:center; font-size:12px; color:#9ca3af; padding:16px; }
</style>
"""

def render_session_html(session, index):
    return f"""
    <div class="session">
      <div class="session-title">Session {index} — {session.get('subject','')} ({session.get('duration_mins','')} mins)</div>
      <div class="session-row"><span class="session-label">Topic:</span> {session.get('topic','')}</div>
      <div class="session-row"><span class="session-label">Technique:</span> {session.get('technique','')}</div>
      <div class="session-row"><span class="session-label">Instructions:</span> {session.get('instructions','')}</div>
      <div class="session-row"><span class="session-label">Why it works:</span> {session.get('why_it_works','')}</div>
    </div>
    """

def render_day_html(day):
    if day.get("rest_day"):
        return f"""
        <div class="day-block">
          <div class="day-title">{day.get('day','').upper()} — {day.get('date','')}</div>
          <div class="rest-banner">🌟 Rest day — no revision today. Rest is part of the plan.</div>
        </div>
        """
    sessions_html = "".join(
        render_session_html(s, i) for i, s in enumerate(day.get("sessions", []), 1)
    )
    return f"""
    <div class="day-block">
      <div class="day-title">{day.get('day','').upper()} — {day.get('date','')}</div>
      <div class="day-meta">Total revision time: {day.get('total_mins','')} mins</div>
      {sessions_html}
      <div class="encouragement">✨ {day.get('encouragement','')}</div>
    </div>
    """

def format_plan_for_email_html(plan_json, student_name):
    try:
        days_html = "".join(render_day_html(d) for d in plan_json.get("plan", []))
        return f"""
        <html><head>{EMAIL_STYLE}</head><body>
        <div class="container">
          <div class="header"><h1>📚 Your Personalised Revision Plan, {student_name}!</h1></div>
          <div class="card">{days_html}</div>
          <div class="footer">PlanMyRevision — helping you revise smarter, not harder.</div>
        </div>
        </body></html>
        """
    except Exception:
        return None

def format_plan_for_email_text(plan_json, student_name):
    try:
        output = f"Hi {student_name}! Here is your personalised revision plan:\n\n"
        output += "=" * 50 + "\n\n"
        for day in plan_json.get("plan", []):
            output += f"{day['day'].upper()} {day['date']}\n"
            if day.get("rest_day"):
                output += "REST DAY — No revision today. Rest is part of the plan.\n\n"
                continue
            output += f"Total revision time: {day['total_mins']} mins\n\n"
            for i, session in enumerate(day.get("sessions", []), 1):
                output += f"SESSION {i} — {session['subject']} — {session['duration_mins']} mins\n"
                output += f"Topic: {session['topic']}\n"
                output += f"Technique: {session['technique']}\n"
                output += f"Instructions: {session['instructions']}\n"
                output += f"Why this works for you: {session['why_it_works']}\n\n"
            output += f"{day['encouragement']}\n"
            output += "-" * 50 + "\n\n"
        return output
    except Exception as e:
        return f"Plan generated but formatting failed: {e}"

def format_todays_sessions_html(day, student_name):
    if day.get("rest_day"):
        body = f'<div class="rest-banner">🌟 Today is your rest day. No revision — rest is part of the plan. See you tomorrow!</div>'
    else:
        sessions_html = "".join(
            render_session_html(s, i) for i, s in enumerate(day.get("sessions", []), 1)
        )
        body = f"""
        <div class="day-meta">Total revision time: {day.get('total_mins','')} mins</div>
        {sessions_html}
        <div class="encouragement">✨ {day.get('encouragement','')}</div>
        """
    return f"""
    <html><head>{EMAIL_STYLE}</head><body>
    <div class="container">
      <div class="header"><h1>📚 Today's Revision Sessions, {student_name}!</h1></div>
      <div class="card">{body}</div>
      <div class="footer">Good luck today! — PlanMyRevision</div>
    </div>
    </body></html>
    """

def format_todays_sessions_text(day, student_name):
    try:
        if day.get("rest_day"):
            return f"Hi {student_name}! Today is your rest day. No revision — rest is part of the plan. See you tomorrow!"
        output = f"Hi {student_name}! Here are your revision sessions for today:\n\n"
        output += f"{day['day'].upper()} {day['date']}\n"
        output += f"Total revision time: {day['total_mins']} mins\n\n"
        for i, session in enumerate(day.get("sessions", []), 1):
            output += f"SESSION {i} — {session['subject']} — {session['duration_mins']} mins\n"
            output += f"Topic: {session['topic']}\n"
            output += f"Technique: {session['technique']}\n"
            output += f"Instructions: {session['instructions']}\n"
            output += f"Why this works for you: {session['why_it_works']}\n\n"
        output += f"{day['encouragement']}\n\nGood luck today! — PlanMyRevision"
        return output
    except Exception as e:
        return f"Error formatting today's sessions: {e}"

# ---------- EMAIL SENDING ----------

def send_email(to_email, subject, text_body, html_body=None):
    payload = {
        "from": "PlanMyRevision <hello@planmyrevision.com>",
        "to": [to_email],
        "subject": subject,
        "text": text_body
    }
    if html_body:
        payload["html"] = html_body
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {os.getenv('RESEND_API_KEY')}",
            "Content-Type": "application/json"
        },
        json=payload
    )
    return response.status_code == 200

# ---------- SHEET STORAGE ----------

def save_to_sheet(record):
    sheet_url = os.getenv('SHEET_WEBHOOK_URL', '')
    if not sheet_url:
        return
    try:
        requests.post(sheet_url, json=record, timeout=5)
    except Exception:
        pass

def get_last_plan_date(plan_json):
    try:
        days = plan_json.get("plan", [])
        if not days:
            return ''
        return days[-1].get("date", '')
    except Exception:
        return ''

PLAN_LENGTH_RULE = """
PLAN LENGTH RULE (IMPORTANT):
- Only generate a detailed day-by-day plan for the NEXT 4 TO 6 WEEKS from the given start date.
- If the nearest exam is sooner than 4 weeks away, stop the plan the day before that exam instead.
- Do NOT attempt to generate a plan all the way to the final exam in one go if that is more than 6 weeks away — only the next chunk.
- This is a rolling plan: further chunks will be generated automatically as this one runs out, closer to the time.
"""

def build_student_profile_block(data):
    return f"""
STUDENT PROFILE:
- Name: {clean(data.get('name', 'Student'))}
- Year: {clean(data.get('year', 'Year 10'))}
- Exams begin: {clean(data.get('exam_start', 'Unknown'))}
- Daily time available: {clean(data.get('daily_hours', '1-2 hours'))}
- Session preference: {clean(data.get('session_style', 'Mixed'))}
- Reminders: {clean(data.get('reminders', 'no'))}

SUBJECTS, CONFIDENCE RATINGS AND EXAM DATES:
{clean(data.get('subjects', ''))}

ADDITIONAL CONTEXT:
- Distractions: {clean(data.get('distractions', 'Various'))}
- Sleep: {clean(data.get('sleep', 'Unknown'))}
- Prior techniques: {clean(data.get('prior_techniques', 'None'))}
- Additional notes: {clean(data.get('notes', 'None'))}

SCHEDULING RULES:
- Prioritise low confidence subjects with early exam dates most urgently
- Sessions must never exceed 45 minutes each
- Maximum 90 minutes total revision per day
- Never same subject on consecutive days unless it is the weakest subject in week one
- Day before each exam: only that subject, light recall, finish by 7pm
- Exam morning: 15 minute confidence session only
"""

def call_gemini(full_prompt):
    response = requests.post(
        url="https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent",
        headers={
            "x-goog-api-key": os.getenv('GEMINI_API_KEY'),
            "Content-Type": "application/json"
        },
        json={
            "system_instruction": {
                "parts": [{"text": full_prompt}]
            },
            "contents": [
                {"role": "user", "parts": [{"text": "Please generate my personalised revision plan."}]}
            ],
            "generationConfig": {
                "maxOutputTokens": 16000,
                "responseMimeType": "application/json"
            }
        }
    )
    result = response.json()
    try:
        raw_content = result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        raise Exception(f"Gemini did not return a valid response (HTTP {response.status_code}). Full response: {json.dumps(result)}")

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

    try:
        plan_json = json.loads(clean_content)
        return plan_json, None
    except Exception as e:
        return None, raw_content

@app.route('/generate-plan', methods=['POST'])
def generate_plan():
    data = request.json
    today = datetime.now()
    today_str = today.strftime("%A %d %B %Y")
    student_name = clean(data.get('name', 'Student'))
    student_email = clean(data.get('email', ''))

    with open("prompt.txt", "r") as f:
        base_prompt = f.read()

    full_prompt = f"""{base_prompt}

TODAY'S DATE AND TIME CONTEXT:
- Today is {today_str}
- This is the FIRST plan for this student — start from today
- Use this to calculate exactly how many days remain until each exam
- Calculate which days of the week fall on which dates yourself
- Never revise on: {clean(data.get('unavailable_days', 'None'))}
- Stop the revision plan the day before exams begin
- In the final 3 days before each exam, only revise that subject lightly

{PLAN_LENGTH_RULE}
{build_student_profile_block(data)}
"""

    plan_json, raw_fallback = call_gemini(full_prompt)

    if plan_json:
        html_email = format_plan_for_email_html(plan_json, student_name)
        text_email = format_plan_for_email_text(plan_json, student_name)
        last_plan_date = get_last_plan_date(plan_json)
        plan_store = json.dumps(plan_json)
    else:
        html_email = None
        text_email = raw_fallback
        last_plan_date = ''
        plan_store = raw_fallback

    if student_email:
        send_email(
            student_email,
            f"📚 Your Personalised Revision Plan, {student_name}!",
            text_email,
            html_email
        )

    save_to_sheet({
        "name": student_name,
        "email": student_email,
        "reminders": clean(data.get('reminders', 'no')),
        "plan": plan_store,
        "last_plan_date": last_plan_date,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "year": clean(data.get('year', '')),
        "exam_start": clean(data.get('exam_start', '')),
        "daily_hours": clean(data.get('daily_hours', '')),
        "session_style": clean(data.get('session_style', '')),
        "unavailable_days": clean(data.get('unavailable_days', '')),
        "subjects": clean(data.get('subjects', '')),
        "distractions": clean(data.get('distractions', '')),
        "sleep": clean(data.get('sleep', '')),
        "prior_techniques": clean(data.get('prior_techniques', '')),
        "notes": clean(data.get('notes', ''))
    })

    return jsonify({
        "status": "success",
        "plan_json": plan_store,
        "last_plan_date": last_plan_date,
        "student_name": student_name,
        "student_email": student_email
    })

@app.route('/continue-plan', methods=['POST'])
def continue_plan():
    """
    Called by Make.com when a student's current plan chunk is about to run out.
    Expects the same fields as /generate-plan, PLUS 'last_plan_date' (the last
    date already covered by the previous chunk) pulled from the Google Sheet row.
    """
    data = request.json
    student_name = clean(data.get('name', 'Student'))
    student_email = clean(data.get('email', ''))
    last_plan_date = clean(data.get('last_plan_date', ''))

    with open("prompt.txt", "r") as f:
        base_prompt = f.read()

    full_prompt = f"""{base_prompt}

TODAY'S DATE AND TIME CONTEXT:
- This is a CONTINUATION of an existing plan, not a first-time plan
- The student's previous plan chunk already covers every day up to and including {last_plan_date}
- Start this new chunk the day AFTER {last_plan_date}
- Calculate which days of the week fall on which dates yourself
- Never revise on: {clean(data.get('unavailable_days', 'None'))}
- Stop the revision plan the day before exams begin
- In the final 3 days before each exam, only revise that subject lightly
- Keep subject rotation varied and do not assume what was covered before beyond what these rules already imply

{PLAN_LENGTH_RULE}
{build_student_profile_block(data)}
"""

    plan_json, raw_fallback = call_gemini(full_prompt)

    if plan_json:
        html_email = format_plan_for_email_html(plan_json, student_name)
        text_email = format_plan_for_email_text(plan_json, student_name)
        new_last_plan_date = get_last_plan_date(plan_json)
        plan_store = json.dumps(plan_json)
    else:
        html_email = None
        text_email = raw_fallback
        new_last_plan_date = last_plan_date
        plan_store = raw_fallback

    if student_email:
        send_email(
            student_email,
            f"📚 Your Next Revision Plan Chunk, {student_name}!",
            text_email,
            html_email
        )

    save_to_sheet({
        "name": student_name,
        "email": student_email,
        "reminders": clean(data.get('reminders', 'no')),
        "plan": plan_store,
        "last_plan_date": new_last_plan_date,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "year": clean(data.get('year', '')),
        "exam_start": clean(data.get('exam_start', '')),
        "daily_hours": clean(data.get('daily_hours', '')),
        "session_style": clean(data.get('session_style', '')),
        "unavailable_days": clean(data.get('unavailable_days', '')),
        "subjects": clean(data.get('subjects', '')),
        "distractions": clean(data.get('distractions', '')),
        "sleep": clean(data.get('sleep', '')),
        "prior_techniques": clean(data.get('prior_techniques', '')),
        "notes": clean(data.get('notes', ''))
    })

    return jsonify({
        "status": "success",
        "plan_json": plan_store,
        "last_plan_date": new_last_plan_date,
        "student_name": student_name,
        "student_email": student_email
    })

@app.route('/todays-sessions', methods=['POST'])
def todays_sessions():
    data = request.json
    student_name = clean(data.get('name', 'Student'))
    student_email = clean(data.get('email', ''))
    plan_json_str = data.get('plan_json', '')

    today_str = datetime.now().strftime("%Y-%m-%d")

    try:
        plan_json = json.loads(plan_json_str)
        today_day = None
        for day in plan_json.get("plan", []):
            if day.get("date") == today_str:
                today_day = day
                break

        if not today_day:
            return jsonify({
                "status": "no_session",
                "message": f"No session found for today ({today_str})"
            })

        html_body = format_todays_sessions_html(today_day, student_name)
        text_body = format_todays_sessions_text(today_day, student_name)

        if student_email:
            send_email(
                student_email,
                f"📚 Today's Revision Sessions — {today_day['day']}",
                text_body,
                html_body
            )

        return jsonify({
            "status": "success",
            "todays_plan": text_body,
            "date": today_str
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "running"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
