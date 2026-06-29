from database.db import (

    save_assignment,

    get_assignments,

    get_teacher_assignments,

    get_student_assignments,

    get_assignment,

    get_latest_active_assignment,

    cursor,

    conn
)

# =========================
# CREATE ASSIGNMENT
# =========================

def create_assignment(

    student,
    task,
    deadline,
    teacher=None
):

    assignment_id = save_assignment(

        student,
        task,
        deadline,
        teacher
    )

    return {

        "success": True,

        "assignment_id": assignment_id,

        "message":
        f"Assignment created for {student}"
    }

# =========================
# FETCH ALL ASSIGNMENTS
# =========================

def fetch_all_assignments():

    assignments = get_assignments()

    return assignments

def fetch_teacher_assignments(teacher):

    return get_teacher_assignments(teacher)

# =========================
# FETCH STUDENT ASSIGNMENTS
# =========================

def fetch_student_assignments(
    student
):

    assignments = get_student_assignments(
        student
    )

    return assignments

def fetch_assignment(assignment_id):

    return get_assignment(assignment_id)

def fetch_latest_active_assignment(student):

    return get_latest_active_assignment(student)

# =========================
# UPDATE ASSIGNMENT STATUS
# =========================

def update_assignment_status(

    assignment_id,
    status
):

    cursor.execute(

        """
        UPDATE assignments

        SET status=?

        WHERE id=?
        """,

        (
            status,
            assignment_id
        )
    )

    conn.commit()

    return {

        "success": True,

        "message":
        "Assignment status updated"
    }
