from services.ai_service import (
    client
)

from database.db import (
    get_student_performance
)

# =========================
# AI PERFORMANCE SUMMARY
# =========================

def generate_student_summary(student):

    if client is None:

        return {

            "success": False,

            "summary":
            "❌ GROQ_API_KEY not configured"
        }

    try:

        data = get_student_performance(
            student
        )

        if not data:

            return {

                "success": False,

                "summary":
                "No performance data found."
            }

        attendance_percentage = 0

        if data["total_attendance"] > 0:

            attendance_percentage = (

                data["present"]
                /
                data["total_attendance"]

            ) * 100

        marks_text = ""

        weak_subjects = []

        for subject, score in data.get("marks", []):

            marks_text += f"{subject}: {score}\n"

            if score < 50:

                weak_subjects.append(subject)

        weak_text = ", ".join(weak_subjects) if weak_subjects else "None"

        prompt = f"""

Analyze this student performance.

Student:
{student}

Attendance:
{attendance_percentage:.1f}%

Assignments:
{data["assignments"]}

Submissions:
{data["submissions"]}

Marks:
{marks_text}

Weak Subjects:
{weak_text}

Generate:

1. Overall performance
2. Strengths
3. Weak areas
4. Improvement suggestions
5. Motivation message

Keep response:
- short
- professional
- teacher-friendly
"""

        completion = (

            client.chat.completions.create(

                model=
                "llama-3.3-70b-versatile",

                messages=[

                    {

                        "role": "system",

                        "content":
                        "You are an AI academic performance analyst."
                    },

                    {

                        "role": "user",

                        "content": prompt
                    }
                ],

                temperature=0.5,

                max_tokens=500
            )
        )

        answer = (

            completion
            .choices[0]
            .message
            .content
        )

        return {

            "success": True,

            "summary": answer
        }

    except Exception as e:

        print(e)

        return {

            "success": False,

            "summary":
            "❌ AI summary unavailable"
        }
