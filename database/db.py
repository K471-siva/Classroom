import sqlite3
import secrets
from datetime import datetime, timezone
from passlib.context import CryptContext


def utcnow_iso():
    """
    Naive UTC timestamp in ISO format (seconds precision).

    Replaces the deprecated datetime.utcnow() while keeping the EXACT same
    string format the rest of the code (and the reminder scheduler) expects,
    so stored timestamps stay comparable.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


# =========================
# PASSWORD HASHING
# =========================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)

# =========================
# DATABASE CONNECTION
# =========================

conn = sqlite3.connect(
    "classroom.db",
    check_same_thread=False,
    timeout=30
)

cursor = conn.cursor()

# WAL mode + busy timeout let the bot process and the web dashboard process
# read/write the same SQLite file concurrently without "database is locked".
cursor.execute("PRAGMA journal_mode=WAL")
cursor.execute("PRAGMA busy_timeout=30000")

# =========================
# USERS TABLE
# =========================

cursor.execute("""

CREATE TABLE IF NOT EXISTS users(

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT,

    username TEXT UNIQUE,

    password TEXT,

    role TEXT,

    telegram_id TEXT
)

""")

conn.commit()

cursor.execute("""

CREATE TABLE IF NOT EXISTS teacher_profiles(

    username TEXT PRIMARY KEY,

    full_name TEXT,

    email TEXT,

    phone TEXT,

    bio TEXT,

    profile_image TEXT
)

""")

conn.commit()

cursor.execute("""

CREATE TABLE IF NOT EXISTS student_profiles(

    username TEXT PRIMARY KEY,

    full_name TEXT,

    email TEXT,

    phone TEXT,

    profile_image TEXT
)

""")

conn.commit()

cursor.execute("""

CREATE TABLE IF NOT EXISTS chat_history(

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    username TEXT,

    role TEXT,

    message TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)

""")

conn.commit()

# =========================
# ASSIGNMENTS TABLE
# =========================

cursor.execute("""

CREATE TABLE IF NOT EXISTS assignments(

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    student TEXT,

    task TEXT,

    deadline TEXT,

    status TEXT DEFAULT 'Pending'
)

""")

for column_sql in [
    "ALTER TABLE assignments ADD COLUMN teacher TEXT",
    "ALTER TABLE assignments ADD COLUMN created_at TEXT",
    "ALTER TABLE assignments ADD COLUMN last_progress TEXT",
    "ALTER TABLE assignments ADD COLUMN last_progress_at TEXT",
    "ALTER TABLE assignments ADD COLUMN reminder_count INTEGER DEFAULT 0",
    "ALTER TABLE assignments ADD COLUMN last_reminded_at TEXT",
]:
    try:
        cursor.execute(column_sql)
    except sqlite3.OperationalError:
        pass

# =========================
# SUBMISSIONS TABLE
# =========================

cursor.execute("""

CREATE TABLE IF NOT EXISTS submissions(

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    assignment_id INTEGER,

    student TEXT,

    file_path TEXT,

    feedback TEXT DEFAULT 'Pending Review',

    status TEXT DEFAULT 'Submitted'
)

""")

for column_sql in [
    "ALTER TABLE submissions ADD COLUMN text_content TEXT",
    "ALTER TABLE submissions ADD COLUMN created_at TEXT",
]:
    try:
        cursor.execute(column_sql)
    except sqlite3.OperationalError:
        pass

cursor.execute("""

CREATE TABLE IF NOT EXISTS teacher_students(

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    teacher TEXT,

    student TEXT,

    invite_code TEXT UNIQUE,

    status TEXT DEFAULT 'invited',

    created_at TEXT
)

""")

cursor.execute("""

CREATE TABLE IF NOT EXISTS progress_updates(

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    assignment_id INTEGER,

    student TEXT,

    message TEXT,

    status TEXT,

    created_at TEXT
)

""")

# =========================
# MARKS TABLE
# =========================

cursor.execute("""

CREATE TABLE IF NOT EXISTS marks(

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    student TEXT,

    subject TEXT,

    score INTEGER

)

""")

conn.commit()
# =========================
# NOTIFICATIONS TABLE
# =========================

cursor.execute("""

CREATE TABLE IF NOT EXISTS notifications(

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    student TEXT,

    message TEXT
)

""")

conn.commit()

# =========================
# HASH PASSWORD
# =========================

def hash_password(password):

    return pwd_context.hash(password)

# =========================
# VERIFY PASSWORD
# =========================

def verify_password(
    plain_password,
    hashed_password
):

    return pwd_context.verify(
        plain_password,
        hashed_password
    )

# =========================
# REGISTER USER
# =========================

def register_user(
    name,
    username,
    password,
    role
):

    try:

        hashed_password = hash_password(
            password
        )

        cursor.execute(

            """
            INSERT INTO users(
                name,
                username,
                password,
                role
            )

            VALUES(?,?,?,?)
            """,

            (
                name,
                username,
                hashed_password,
                role
            )
        )

        conn.commit()

        return True

    except Exception as e:

        print(e)

        return False

# =========================
# LOGIN USER
# =========================

def login_user(
    username,
    password
):

    cursor.execute(

        """
        SELECT * FROM users
        WHERE username=?
        """,

        (username,)
    )

    user = cursor.fetchone()

    if not user:

        return None

    valid = verify_password(
        password,
        user[3]
    )

    if valid:

        return user

    return None
# =========================
# GET TELEGRAM ID
# =========================

def get_telegram_id(username):

    cursor.execute(

        """
        SELECT telegram_id

        FROM users

        WHERE username=?
        """,

        (username,)
    )

    result = cursor.fetchone()

    if result:

        return result[0]

    return None

def get_user_by_telegram_id(telegram_id):

    cursor.execute(
        """
        SELECT *
        FROM users
        WHERE telegram_id=?
        """,
        (str(telegram_id),)
    )

    return cursor.fetchone()
# =========================
# SAVE TELEGRAM ID
# =========================

def update_telegram_id(

    username,
    telegram_id

):

    cursor.execute(

        """
        UPDATE users

        SET telegram_id=?

        WHERE username=?
        """,

        (
            telegram_id,
            username
        )
    )

    conn.commit()
# =========================
# SAVE ASSIGNMENT
# =========================

def save_assignment(
    student,
    task,
    deadline,
    teacher=None
):

    cursor.execute(

        """
        INSERT INTO assignments(
            student,
            task,
            deadline,
            teacher,
            created_at
        )

        VALUES(?,?,?,?,?)
        """,

        (
            student,
            task,
            deadline,
            teacher,
            utcnow_iso()
        )
    )

    conn.commit()

    return cursor.lastrowid

# =========================
# GET ASSIGNMENTS
# =========================

def get_assignments():

    cursor.execute(
        """
        SELECT * FROM assignments
        ORDER BY id DESC
        """
    )

    return cursor.fetchall()

def get_teacher_assignments(teacher):

    cursor.execute(
        """
        SELECT *
        FROM assignments
        WHERE teacher=? OR teacher IS NULL
        ORDER BY id DESC
        """,
        (teacher,)
    )

    return cursor.fetchall()

# =========================
# GET STUDENT ASSIGNMENTS
# =========================

def get_student_assignments(student):

    cursor.execute(

        """
        SELECT * FROM assignments
        WHERE student=?
        ORDER BY id DESC
        """,

        (student,)
    )

    return cursor.fetchall()

def get_assignment(assignment_id):

    cursor.execute(
        """
        SELECT *
        FROM assignments
        WHERE id=?
        """,
        (assignment_id,)
    )

    return cursor.fetchone()

def get_latest_active_assignment(student):

    cursor.execute(
        """
        SELECT *
        FROM assignments
        WHERE student=?
        AND status NOT IN ('Completed', 'Reviewed')
        ORDER BY id DESC
        LIMIT 1
        """,
        (student,)
    )

    return cursor.fetchone()

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

# =========================
# GET PENDING ASSIGNMENTS
# =========================

def get_pending_assignments():

    cursor.execute(

        """
        SELECT id,
               student,
               task,
               deadline,
               status,
               reminder_count,
               last_reminded_at

        FROM assignments

        WHERE status IN ('Pending', 'In Progress')
        """
    )

    return cursor.fetchall()

# =========================
# SAVE SUBMISSION
# =========================

def save_submission(

    assignment_id,
    student,
    file_path,
    text_content=None

):

    cursor.execute(

        """
        SELECT id

        FROM submissions

        WHERE assignment_id=?
        AND student=?
        """,

        (
            assignment_id,
            student
        )
    )

    existing = cursor.fetchone()

    if existing:
        return existing[0]

    cursor.execute(

        """
        INSERT INTO submissions(

            assignment_id,
            student,
            file_path,
            text_content,
            created_at

        )

        VALUES(?,?,?,?,?)
        """,

        (
            assignment_id,
            student,
            file_path,
            text_content,
            utcnow_iso()
        )
    )

    conn.commit()

    cursor.execute(
    """
    UPDATE assignments
    SET status='Submitted'
    WHERE id=?
    """,
    (assignment_id,)
)

    conn.commit()

    return cursor.lastrowid
    
# =========================
# GET STUDENT SUBMISSIONS
# =========================

def get_student_submissions(student):

    cursor.execute(

        """
        SELECT * FROM submissions
        WHERE student=?
        ORDER BY id DESC
        """,

        (student,)
    )

    return cursor.fetchall()

# =========================
# GET ALL SUBMISSIONS
# =========================

def get_all_submissions():

    cursor.execute(
        """
        SELECT * FROM submissions
        ORDER BY id DESC
        """
    )

    return cursor.fetchall()

# =========================
# ATTENDANCE TABLE
# =========================

cursor.execute("""

CREATE TABLE IF NOT EXISTS attendance(

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    student TEXT,

    date TEXT,

    status TEXT

)

""")

conn.commit()
# =========================
# MARK ATTENDANCE
# =========================

def mark_attendance(

    student,
    date,
    status

):

    cursor.execute(

        """
        SELECT id

        FROM attendance

        WHERE student=?
        AND date=?
        """,

        (
            student,
            date
        )
    )

    existing = cursor.fetchone()

    if existing:

        return

    cursor.execute(

        """
        INSERT INTO attendance(

            student,
            date,
            status

        )

        VALUES(?,?,?)
        """,

        (
            student,
            date,
            status
        )
    )

    conn.commit()

# =========================
# GET STUDENT ATTENDANCE
# =========================

def get_student_attendance(student):

    cursor.execute(

        """
        SELECT * FROM attendance

        WHERE student=?

        ORDER BY id DESC
        """,

        (student,)
    )

    return cursor.fetchall()

# =========================
# ATTENDANCE PERCENTAGE
# =========================

def attendance_percentage(student):

    cursor.execute(

        """
        SELECT COUNT(*)

        FROM attendance

        WHERE student=?
        """,

        (student,)
    )

    total = cursor.fetchone()[0]

    cursor.execute(

        """
        SELECT COUNT(*)

        FROM attendance

        WHERE student=?
        AND status='Present'
        """,

        (student,)
    )

    present = cursor.fetchone()[0]

    if total == 0:

        return 0

    percentage = int(

        (present / total) * 100
    )

    return percentage

# =========================
# CREATE NOTIFICATION
# =========================

def create_notification(

    student,
    message

):

    cursor.execute(

        """
        INSERT INTO notifications(

            student,
            message

        )

        VALUES(?,?)
        """,

        (
            student,
            message
        )
    )

    conn.commit()

# =========================
# GET NOTIFICATIONS
# =========================

def get_notifications(student):

    cursor.execute(

        """
        SELECT * FROM notifications

        WHERE student=?

        ORDER BY id DESC
        """,

        (student,)
    )

    return cursor.fetchall()

# =========================
# TOTAL ASSIGNMENTS
# =========================

def total_assignments():

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM assignments
        """
    )

    return cursor.fetchone()[0]

# =========================
# TOTAL STUDENTS
# =========================

def total_students():

    cursor.execute(

        """
        SELECT COUNT(*)

        FROM users

        WHERE role='student'
        """
    )

    return cursor.fetchone()[0]

# =========================
# PENDING ASSIGNMENTS
# =========================

def pending_assignments(student):

    cursor.execute(

        """
        SELECT COUNT(*)

        FROM assignments

        WHERE student=?
        AND status='Pending'
        """,

        (student,)
    )

    return cursor.fetchone()[0]
# =========================
# UPDATE SUBMISSION FEEDBACK
# =========================

def update_submission_feedback(
    submission_id,
    feedback,
    status
):

    cursor.execute(
        """
        UPDATE submissions
        SET feedback=?,
            status=?
        WHERE id=?
        """,
        (
            feedback,
            status,
            submission_id
        )
    )

    cursor.execute(
        """
        SELECT assignment_id
        FROM submissions
        WHERE id=?
        """,
        (submission_id,)
    )

    assignment = cursor.fetchone()

    if assignment:

        cursor.execute(
            """
            UPDATE assignments
            SET status='Completed'
            WHERE id=?
            """,
            (assignment[0],)
        )

    conn.commit()

def create_invite_code(teacher, student):

    code = secrets.token_hex(3).upper()

    cursor.execute(
        """
        INSERT INTO teacher_students(
            teacher,
            student,
            invite_code,
            created_at
        )
        VALUES(?,?,?,?)
        """,
        (
            teacher,
            student,
            code,
            utcnow_iso()
        )
    )

    conn.commit()

    return code

def ensure_teacher_invite_slots(teacher, count=10):

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM teacher_students
        WHERE teacher=?
        """,
        (teacher,)
    )

    existing = cursor.fetchone()[0]

    for _ in range(max(0, count - existing)):

        create_invite_code(teacher, "")

    return get_teacher_students(teacher)

def link_student_to_teacher(invite_code, telegram_id=None, student_name=None):

    cursor.execute(
        """
        SELECT teacher, student
        FROM teacher_students
        WHERE invite_code=?
        """,
        (invite_code.upper(),)
    )

    link = cursor.fetchone()

    if not link:
        return None

    teacher, student = link

    if not student:
        student = student_name or f"student_{telegram_id}"

    cursor.execute(
        """
        UPDATE teacher_students
        SET student=?,
            status='linked'
        WHERE invite_code=?
        """,
        (student, invite_code.upper())
    )

    cursor.execute(
        """
        INSERT OR IGNORE INTO users(name, username, password, role, telegram_id)
        VALUES(?,?,?,?,?)
        """,
        (student, student, "", "student", telegram_id)
    )

    if telegram_id:
        update_telegram_id(student, telegram_id)

    conn.commit()

    return {
        "teacher": teacher,
        "student": student
    }

def get_invite(invite_code):
    """Return (teacher, student, status) for an invite code, or None."""

    cursor.execute(
        """
        SELECT teacher, student, status
        FROM teacher_students
        WHERE invite_code=?
        """,
        (invite_code.upper(),)
    )

    return cursor.fetchone()


def register_invited_student(invite_code, name, username, password, role="student"):
    """
    Link-based student onboarding.

    Validates the invite, creates a real student account WITH a hashed
    password (so the student can log into the web dashboard), and marks the
    invite as linked to that student. Returns a dict describing the outcome.
    """

    invite = get_invite(invite_code)

    if not invite:
        return {"ok": False, "error": "invalid_invite"}

    teacher, _slot_student, status = invite

    if status == "linked":
        return {"ok": False, "error": "invite_used"}

    # Username must be unique across all users.
    cursor.execute(
        "SELECT id FROM users WHERE username=?",
        (username,)
    )

    if cursor.fetchone():
        return {"ok": False, "error": "username_taken"}

    hashed = hash_password(password)

    cursor.execute(
        """
        INSERT INTO users(name, username, password, role)
        VALUES(?,?,?,?)
        """,
        (name, username, hashed, role)
    )

    # Bind this invite to the freshly registered student.
    cursor.execute(
        """
        UPDATE teacher_students
        SET student=?, status='linked'
        WHERE invite_code=?
        """,
        (username, invite_code.upper())
    )

    conn.commit()

    return {"ok": True, "teacher": teacher, "student": username}


def is_student_linked(student, teacher=None):
    """
    True if the student has completed invite registration (status='linked').
    If teacher is given, the link must be to that specific teacher.
    """

    if teacher:
        cursor.execute(
            """
            SELECT 1 FROM teacher_students
            WHERE student=? AND teacher=? AND status='linked'
            LIMIT 1
            """,
            (student, teacher)
        )
    else:
        cursor.execute(
            """
            SELECT 1 FROM teacher_students
            WHERE student=? AND status='linked'
            LIMIT 1
            """,
            (student,)
        )

    return cursor.fetchone() is not None


def get_teacher_students(teacher):

    cursor.execute(
        """
        SELECT student, invite_code, status, created_at
        FROM teacher_students
        WHERE teacher=?
        ORDER BY id DESC
        """,
        (teacher,)
    )

    return cursor.fetchall()

def get_teacher_linked_students(teacher):

    cursor.execute(
        """
        SELECT student, invite_code, status, created_at
        FROM teacher_students
        WHERE teacher=?
        AND status='linked'
        ORDER BY student
        """,
        (teacher,)
    )

    return cursor.fetchall()

def remove_teacher_student(teacher, student):

    cursor.execute(
        """
        DELETE FROM teacher_students
        WHERE teacher=?
        AND student=?
        """,
        (teacher, student)
    )

    conn.commit()

    return cursor.rowcount

def get_submission(submission_id):

    cursor.execute(
        """
        SELECT *
        FROM submissions
        WHERE id=?
        """,
        (submission_id,)
    )

    return cursor.fetchone()

def get_student_teacher(student):

    cursor.execute(
        """
        SELECT teacher
        FROM teacher_students
        WHERE student=?
        AND status='linked'
        ORDER BY id DESC
        LIMIT 1
        """,
        (student,)
    )

    row = cursor.fetchone()

    return row[0] if row else None

def add_progress_update(assignment_id, student, message, status):

    now = utcnow_iso()

    cursor.execute(
        """
        INSERT INTO progress_updates(
            assignment_id,
            student,
            message,
            status,
            created_at
        )
        VALUES(?,?,?,?,?)
        """,
        (assignment_id, student, message, status, now)
    )

    cursor.execute(
        """
        UPDATE assignments
        SET status=?,
            last_progress=?,
            last_progress_at=?
        WHERE id=?
        """,
        (status, message, now, assignment_id)
    )

    conn.commit()

def get_assignment_progress(assignment_id):

    cursor.execute(
        """
        SELECT *
        FROM progress_updates
        WHERE assignment_id=?
        ORDER BY id DESC
        """,
        (assignment_id,)
    )

    return cursor.fetchall()

def get_teacher_progress_updates(teacher):

    cursor.execute(
        """
        SELECT p.*
        FROM progress_updates p
        JOIN assignments a ON a.id = p.assignment_id
        WHERE a.teacher=?
        ORDER BY p.id DESC
        LIMIT 30
        """,
        (teacher,)
    )

    return cursor.fetchall()

def mark_assignment_reminded(assignment_id):

    cursor.execute(
        """
        UPDATE assignments
        SET reminder_count=COALESCE(reminder_count, 0) + 1,
            last_reminded_at=?
        WHERE id=?
        """,
        (
            utcnow_iso(),
            assignment_id
        )
    )

    conn.commit()

# =========================
# SAVE MARKS
# =========================

def save_marks(

    student,
    subject,
    score

):

    cursor.execute(

        """
        INSERT INTO marks(

            student,
            subject,
            score

        )

        VALUES(?,?,?)
        """,

        (
            student,
            subject,
            score
        )
    )

    conn.commit()

# =========================
# GET STUDENT MARKS
# =========================

def get_student_marks(student):

    cursor.execute(

        """
        SELECT *

        FROM marks

        WHERE student=?
        """,

        (student,)
    )

    return cursor.fetchall()
# =========================
# ATTENDANCE ANALYTICS
# =========================

def attendance_analytics(student):

    cursor.execute(

        """
        SELECT COUNT(*)

        FROM attendance

        WHERE student=?
        AND status='Present'
        """,

        (student,)
    )

    present = cursor.fetchone()[0]

    cursor.execute(

        """
        SELECT COUNT(*)

        FROM attendance

        WHERE student=?
        AND status='Absent'
        """,

        (student,)
    )

    absent = cursor.fetchone()[0]

    return {

        "present": present,

        "absent": absent
    }

# =========================
# MARKS ANALYTICS
# =========================

def marks_analytics(student):

    cursor.execute(

        """
        SELECT subject, score

        FROM marks

        WHERE student=?
        """,

        (student,)
    )

    return cursor.fetchall()

# =========================
# ASSIGNMENT ANALYTICS
# =========================

def assignment_analytics(student):

    cursor.execute(

        """
        SELECT COUNT(*)

        FROM assignments

        WHERE student=?
        """,

        (student,)
    )

    total = cursor.fetchone()[0]

    cursor.execute(

        """
        SELECT COUNT(*)

        FROM submissions

        WHERE student=?
        AND status='Reviewed'
        """,

        (student,)
    )

    completed = cursor.fetchone()[0]

    cursor.execute(

        """
        SELECT COUNT(*)

        FROM submissions

        WHERE student=?
        AND status!='Reviewed'
        """,

        (student,)
    )

    submitted = cursor.fetchone()[0]

    pending = total - completed - submitted

    return {

        "completed": completed,

        "submitted": submitted,

        "pending": pending
    }
# =========================
# STUDENT PERFORMANCE DATA
# =========================

def get_student_performance(student):

    # =========================
    # ATTENDANCE
    # =========================

    cursor.execute(

        """
        SELECT COUNT(*)

        FROM attendance

        WHERE student=?
        AND status='Present'
        """,

        (student,)
    )

    present = cursor.fetchone()[0]

    cursor.execute(

        """
        SELECT COUNT(*)

        FROM attendance

        WHERE student=?
        """,

        (student,)
    )

    total_attendance = cursor.fetchone()[0]

    # =========================
    # MARKS
    # =========================

    cursor.execute(

        """
        SELECT subject, score

        FROM marks

        WHERE student=?
        """,

        (student,)
    )

    marks = cursor.fetchall()

    # =========================
    # ASSIGNMENTS
    # =========================

    cursor.execute(

        """
        SELECT COUNT(*)

        FROM assignments

        WHERE student=?
        """,

        (student,)
    )

    assignments = cursor.fetchone()[0]

    # =========================
    # SUBMISSIONS
    # =========================

    cursor.execute(

        """
        SELECT COUNT(*)

        FROM submissions

        WHERE student=?
        """,

        (student,)
    )

    submissions = cursor.fetchone()[0]

    return {

        "present":
        present,

        "total_attendance":
        total_attendance,

        "marks":
        marks,

        "assignments":
        assignments,

        "submissions":
        submissions
    }
# =========================
# CLASSROOM TABLE
# =========================

cursor.execute("""

CREATE TABLE IF NOT EXISTS classrooms(

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    class_name TEXT,

    teacher TEXT,

    group_id TEXT
)

""")

conn.commit()
# =========================
# CREATE CLASSROOM
# =========================

def create_classroom(

    class_name,
    teacher,
    group_id

):

    cursor.execute(

        """
        SELECT id

        FROM classrooms

        WHERE group_id=?
        """,

        (group_id,)
    )

    existing = cursor.fetchone()

    if existing:

        return

    cursor.execute(

        """
        INSERT INTO classrooms(

            class_name,
            teacher,
            group_id

        )

        VALUES(?,?,?)
        """,

        (
            class_name,
            teacher,
            group_id
        )
    )

    conn.commit()

# =========================
# GET CLASSROOM
# =========================

def get_classroom(group_id):

    cursor.execute(

        """
        SELECT *

        FROM classrooms

        WHERE group_id=?
        """,

        (group_id,)
    )

    return cursor.fetchone()

def get_teacher_profile_image(username):
    cursor.execute(
        "SELECT profile_image FROM teacher_profiles WHERE username=?",
        (username,)
    )
    row = cursor.fetchone()
    return row[0] if row and row[0] else None

def get_student_profile_image(username):
    cursor.execute(
        "SELECT profile_image FROM student_profiles WHERE username=?",
        (username,)
    )
    row = cursor.fetchone()
    return row[0] if row and row[0] else None

def close_connection():

    conn.close()
