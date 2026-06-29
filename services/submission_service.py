from database.db import (

    save_submission,

    get_student_submissions,

    get_all_submissions,

    update_submission_feedback
)

# =========================
# CREATE SUBMISSION
# =========================

def create_submission(

    assignment_id,
    student,
    file_path,
    text_content=None

):

    submission_id = save_submission(

        assignment_id,
        student,
        file_path,
        text_content
    )

    return {

        "success": True,

        "submission_id": submission_id,

        "message":
        "Homework submitted successfully"
    }

# =========================
# FETCH STUDENT SUBMISSIONS
# =========================

def fetch_student_submissions(student):

    return get_student_submissions(
        student
    )

# =========================
# FETCH ALL SUBMISSIONS
# =========================

def fetch_all_submissions():

    return get_all_submissions()

# =========================
# REVIEW SUBMISSION
# =========================

def review_submission(

    submission_id,
    feedback

):

    try:

        update_submission_feedback(

            submission_id,
            feedback,
            "Reviewed"
        )

        return {

            "success": True,

            "message":
            "Submission reviewed successfully"
        }

    except Exception as e:

        print(e)

        return {

            "success": False,

            "message":
            str(e)
        }
