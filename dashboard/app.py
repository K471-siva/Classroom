try:
    from fastapi import (
        FastAPI,
        Request,
        Form,
        UploadFile,
        File,
        WebSocket,
        WebSocketDisconnect,
    )
    from fastapi.responses import RedirectResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates
    from starlette.middleware.sessions import SessionMiddleware
except Exception as e:
    # Provide a clearer runtime error when dependencies are missing during development
    raise ImportError(
        "Required dependency 'fastapi' or 'starlette' is not installed. "
        "Install with: pip install fastapi[all] starlette\nOriginal error: {}".format(e)
    )

import shutil

import os

import asyncio

import time

from dotenv import load_dotenv

load_dotenv()



# =========================
# DATABASE
# =========================

from database.db import (

    register_user,
    login_user,
    marks_analytics,
    assignment_analytics,
    total_assignments,
    pending_assignments,
    create_invite_code,
    ensure_teacher_invite_slots,
    get_teacher_linked_students,
    get_teacher_students,
    get_teacher_progress_updates,
    get_submission,
    get_telegram_id,
    remove_teacher_student,
    get_invite,
    register_invited_student,
    is_student_linked,
    get_teacher_profile_image,
    get_student_profile_image

)

# =========================
# SERVICES
# =========================

from services.assignment_service import (

    create_assignment,

    fetch_teacher_assignments,

    fetch_student_assignments
)
from services.telegram_service import (
    send_group_message,
    send_private_message
)
from services.submission_service import (

    create_submission,

    fetch_student_submissions,

    fetch_all_submissions,

    review_submission
)
from services.ai_service import (
    ask_ai
)
from services.performance_ai_service import (

    generate_student_summary
)
from services.reminder_service import (
    reminder_loop
)
# =========================
# FASTAPI
# =========================

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the proactive reminder loop when the server boots.
    task = asyncio.create_task(reminder_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv(
        "SECRET_KEY",
        "sim_classroom_secret"
    ),
    max_age=604800
)

# =========================
# STATIC FILES
# =========================

app.mount(

    "/static",

    StaticFiles(
        directory="dashboard/static"
    ),

    name="static"
)

# Serve uploaded submissions (files/photos) so teachers can open them.
os.makedirs("uploads", exist_ok=True)

app.mount(
    "/uploads",
    StaticFiles(directory="uploads"),
    name="uploads"
)

# =========================
# TEMPLATES
# =========================

templates = Jinja2Templates(
    directory="dashboard/templates"
)

# =========================
# WEBSOCKET MANAGER
# =========================

class ConnectionManager:

    def __init__(self):

        self.active_connections = []

    # CONNECT

    async def connect(

        self,
        websocket: WebSocket

    ):

        await websocket.accept()

        self.active_connections.append(
            websocket
        )

    # DISCONNECT

    def disconnect(
    self,
    websocket: WebSocket
):

        if websocket in self.active_connections:

         self.active_connections.remove(
            websocket
        )

    # BROADCAST

    async def broadcast(

        self,
        message: str

    ):

        disconnected = []

        for connection in self.active_connections:

            try:

                await connection.send_text(
                    message
                )

            except:

                disconnected.append(
                    connection
                )

        for connection in disconnected:

            self.disconnect(
                connection
            )

# GLOBAL MANAGER

manager = ConnectionManager()

def teacher_dashboard_context(teacher, success=None, error=None):

    ensure_teacher_invite_slots(teacher, 10)

    linked_students = get_teacher_linked_students(teacher)

    context = {

        "name": teacher,

        "assignments":
        fetch_teacher_assignments(teacher),

        "submissions":
        fetch_all_submissions(),

        "total_assignments":
        total_assignments(),

        "total_students":
        len(linked_students),

        "students":
        get_teacher_students(teacher),

        "linked_students":
        linked_students,

        "progress_updates":
        get_teacher_progress_updates(teacher),

        "bot_username":
        os.getenv("BOT_USERNAME", ""),

        "group_invite_link":
        os.getenv("TELEGRAM_GROUP_INVITE_LINK", ""),

        "profile_image":
        get_teacher_profile_image(teacher)
    }

    if success:
        context["success"] = success

    if error:
        context["error"] = error

    return context

# =========================
# HOME PAGE
# =========================

@app.get("/")
async def home(
    request: Request
):

    return templates.TemplateResponse(

        request=request,

        name="login.html",

        context={}
    )

# =========================
# LOGIN PAGE
# =========================

@app.get("/login")
async def login_page(
    request: Request
):

    return templates.TemplateResponse(

        request=request,

        name="login.html",

        context={}
    )

# =========================
# REGISTER PAGE
# =========================

@app.get("/register")
async def register_page(
    request: Request
):

    return templates.TemplateResponse(

        request=request,

        name="register.html",

        context={}
    )

# =========================
# REGISTER
# =========================

@app.post("/register")
async def register(

    request: Request,

    name: str = Form(...),

    username: str = Form(...),

    password: str = Form(...),

    role: str = Form("teacher")

):

    # Public self-registration is for teachers only. Students must join
    # through a teacher's invite link (/invite/{code}).
    success = register_user(

        name,
        username,
        password,
        "teacher"
    )

    if success:

        return templates.TemplateResponse(

            request=request,

            name="register.html",

            context={

                "success":
                "✅ Registration Successful"
            }
        )

    return templates.TemplateResponse(

        request=request,

        name="register.html",

        context={

            "error":
            "❌ Username already exists"
        }
        
    )

# =========================
# LOGIN
# =========================

@app.post("/login")
async def login(

    request: Request,

    username: str = Form(...),

    password: str = Form(...),

    selected_role: str = Form("")

):

    user = login_user(
        username,
        password
    )

    if not user:

        return templates.TemplateResponse(

            request=request,

            name="login.html",

            context={

                "error":
                "❌ Invalid username or password",
                "selected_role": role
            }
        )

    role = user[4]

    if selected_role and selected_role != role:

        return templates.TemplateResponse(

            request=request,

            name="login.html",

            context={
                "error":
                f"❌ You selected {selected_role.title()} login, but this username is a {role} account.",
                "selected_role": selected_role
            }
        )

    role = user[4]

    request.session["username"] = username
    request.session["role"] = role

    if role == "teacher":

        return RedirectResponse(
            url="/teacher-dashboard",
            status_code=303
        )

    if role == "student":

        return RedirectResponse(
            url="/student-dashboard",
            status_code=303
        )

# =========================
# TEACHER DASHBOARD ROUTE
# =========================

@app.get("/teacher-dashboard")
async def teacher_dashboard(
    request: Request
):

    if request.session.get("role") != "teacher":

        return RedirectResponse(
            "/login",
            status_code=302
        )

    teacher = request.session.get(
        "username",
        "Teacher"
    )

    return templates.TemplateResponse(

        request=request,

        name="teacher_dashboard.html",

        context=teacher_dashboard_context(teacher)
    )
   
# =========================
# STUDENT DASHBOARD ROUTE
# =========================
@app.get("/invite/{invite_code}")
async def invite_register_page(request: Request, invite_code: str):

    # A student opens this link (shared by their teacher) to self-register.
    invite = get_invite(invite_code)

    # Invalid code -> render the friendly error state.
    if not invite:
        return templates.TemplateResponse(
            request=request,
            name="invite_register.html",
            context={
                "invite_code": invite_code,
                "invite_error": "This invite link is invalid.",
            },
        )

    teacher, slot_student, status = invite

    # Already-used link -> tell them to just log in.
    if status == "linked":
        return templates.TemplateResponse(
            request=request,
            name="invite_register.html",
            context={
                "invite_code": invite_code,
                "invite_error": "This invite link has already been used. Please log in.",
            },
        )

    return templates.TemplateResponse(
        request=request,
        name="invite_register.html",
        context={
            "invite_code": invite_code,
            "invite_error": None,
            "teacher": teacher,
            "student_name": slot_student or "",
        },
    )


@app.post("/invite/{invite_code}/register")
async def invite_register_submit(
    request: Request,
    invite_code: str,
    name: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    student_name: str = Form(""),
):

    invite_code = invite_code.upper()

    # Create a real, password-protected student account AND link it to the
    # inviting teacher in one atomic step.
    result = register_invited_student(invite_code, name, username, password)

    if not result["ok"]:

        messages = {
            "invalid_invite": "This invite link is invalid.",
            "invite_used": "This invite link has already been used. Please log in.",
            "username_taken": "That username is already taken. Try another.",
        }

        return templates.TemplateResponse(
            request=request,
            name="invite_register.html",
            context={
                "invite_code": invite_code,
                "invite_error": None,
                "error": messages.get(result["error"], "Registration failed."),
                "name": name,
                "username": username,
            },
        )

    # Student is now registered AND linked -> send them to login.
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "success": "✅ Registration complete! Log in to see your assignments.",
        },
    )


@app.get("/student-dashboard")
async def student_dashboard(

    request: Request

):
    
    if request.session.get("role") != "student":

        return RedirectResponse(
        "/login",
        status_code=302
    )
    student = request.session.get(
        "username",
        "Student"
    )

    assignments = fetch_student_assignments(student)

    submissions = fetch_student_submissions(
        student
    )

    return templates.TemplateResponse(

        request=request,

        name="student_dashboard.html",

        context={

            "name": student,

            "assignments": assignments,

            "submissions": submissions,

            "total_assignments":
            len(assignments),

            "pending":
            pending_assignments(student),

            "group_invite_link":
            os.getenv("TELEGRAM_GROUP_INVITE_LINK", ""),

            "profile_image":
            get_student_profile_image(student)
        }
    )

# =========================
# CHECK SESSION
# =========================

@app.get("/check-session")
async def check_session(
    request: Request
):

    return {

        "username":
        request.session.get(
            "username"
        ),

        "role":
        request.session.get(
            "role"
        )
    }

# =========================
# LOGOUT
# =========================

@app.get("/logout")
async def logout(
    request: Request
):


    request.session.clear()

    return RedirectResponse(
        url="/"
    )

# =========================
# CREATE ASSIGNMENT
# =========================

@app.post("/assign")
async def assign_homework(

    request: Request,

    student: str = Form(...),

    task: str = Form(...),

    deadline: str = Form(...)

):

    if request.session.get("role") != "teacher":

        return RedirectResponse(
            "/login",
            status_code=302
        )

    student = student.strip()

    teacher = request.session.get(
        "username",
        "Teacher"
    )

    # A teacher can only assign work to students who have completed
    # invite registration (status='linked'). No registration -> no assignment.
    if not is_student_linked(student, teacher):

        return templates.TemplateResponse(

            request=request,

            name="teacher_dashboard.html",

            context=teacher_dashboard_context(
                teacher,
                None,
                f"❌ {student} has not registered yet. Share an invite link and assign once they join."
            )
        )

    result = create_assignment(

           student,
           task,
           deadline,
           teacher
)

            # =========================
        # TELEGRAM GROUP MESSAGE
        # =========================

    group_message = f"""

📚 New Homework Assigned

👤 Student:
{student}

📚 Task:
{task}

⏰ Deadline:
{deadline}
"""

        # SEND TO ALL CLASSROOMS

    from database.db import cursor

    cursor.execute(
            "SELECT group_id FROM classrooms"
        )

    groups = cursor.fetchall()

    for group in groups:

            send_group_message(

                group[0],

                group_message
            )

    # REALTIME

    await manager.broadcast(

        f"""
📚 New Assignment

Student:
{student}

Task:
{task}
"""
    )

    return templates.TemplateResponse(

        request=request,

        name="teacher_dashboard.html",

        context=teacher_dashboard_context(
            teacher,
            result["message"]
        )
    )

# =========================
# ONBOARD STUDENT
# =========================

@app.post("/onboard-student")
async def onboard_student_route(

    request: Request,

    student: str = Form(...)

):

    if request.session.get("role") != "teacher":

        return RedirectResponse(
            "/login",
            status_code=302
        )

    teacher = request.session.get(
        "username",
        "Teacher"
    )

    code = create_invite_code(
        teacher,
        student.strip()
    )

    return templates.TemplateResponse(

        request=request,

        name="teacher_dashboard.html",

        context=teacher_dashboard_context(
            teacher,
            f"Invite created for {student}. Student should send /link {code} in Telegram."
        )
    )

# =========================
# REMOVE STUDENT
# =========================

@app.post("/remove-student")
async def remove_student_route(

    request: Request,

    student: str = Form(...)

):

    if request.session.get("role") != "teacher":

        return RedirectResponse(
            "/login",
            status_code=302
        )

    teacher = request.session.get(
        "username",
        "Teacher"
    )

    removed = remove_teacher_student(
        teacher,
        student
    )

    message = (
        f"{student} removed from your dashboard."
        if removed
        else f"{student} was not found in your student list."
    )

    return templates.TemplateResponse(

        request=request,

        name="teacher_dashboard.html",

        context=teacher_dashboard_context(
            teacher,
            message
        )
    )

# =========================
# SUBMIT HOMEWORK
# =========================

@app.post("/submit-homework")
async def submit_homework(

    request: Request,

    assignment_id: int = Form(...),

    student: str = Form(...),

    file: UploadFile = File(...)

):

    try:

# CREATE FOLDER IF NOT EXISTS

        os.makedirs(

            "uploads/assignments",

            exist_ok=True
        )

        # FILE LOCATION

        file_location = (

    f"uploads/assignments/"

    f"{int(time.time())}_"

    f"{file.filename}"
)

        # SAVE FILE

        with open(

            file_location,

            "wb"

        ) as buffer:

            shutil.copyfileobj(

                file.file,

                buffer
            )

        # SAVE SUBMISSION

        result = create_submission(
              assignment_id,
              student,
                    file_location
)


        print("SUBMISSION CREATED")
        print(student)
        print(file_location)

# REALTIME UPDATE

        await manager.broadcast(

            f"""
📤 Homework Submitted

Student:
{student}

File:
{file.filename}
"""
        )

        assignments = fetch_student_assignments(
            student
        )

        submissions = fetch_student_submissions(
            student
        )

        return templates.TemplateResponse(

            request=request,

            name="student_dashboard.html",

            context={

    "name": student,

    "assignments": assignments,

    "submissions": submissions,

    "total_assignments":
    len(assignments),

    "pending":
    pending_assignments(student),

    "group_invite_link":
    os.getenv("TELEGRAM_GROUP_INVITE_LINK", ""),

    "success":
    "✅ Homework uploaded successfully"
}
        )

    except Exception as e:

        print(e)

        return templates.TemplateResponse(

            request=request,

            name="student_dashboard.html",

            context={

    "name": student,

    "assignments":
    fetch_student_assignments(student),

    "submissions":
    fetch_student_submissions(student),

    "total_assignments":
    len(fetch_student_assignments(student)),

    "pending":
    pending_assignments(student),

    "group_invite_link":
    os.getenv("TELEGRAM_GROUP_INVITE_LINK", ""),

    "error":
    f"❌ Upload failed: {str(e)}"
}
        )

# =========================
# REVIEW SUBMISSION
# =========================

@app.post("/review-submission")
async def review_submission_route(

    request: Request,

    submission_id: int = Form(...),

    feedback: str = Form(...)

):

    if request.session.get("role") != "teacher":

        return RedirectResponse(
            "/login",
            status_code=302
        )

    result = review_submission(

        submission_id,
        feedback
    )

    submission = get_submission(submission_id)

    if submission:

        student_telegram = get_telegram_id(submission[2])

        send_private_message(
            student_telegram,
            f"Your teacher sent feedback:\n\n{feedback}"
        )

    # REALTIME

    await manager.broadcast(

        f"""
✅ Submission Reviewed

Feedback:
{feedback}
"""
    )

    teacher = request.session.get(
        "username",
        "Teacher"
    )

    return templates.TemplateResponse(

        request=request,

        name="teacher_dashboard.html",

        context=teacher_dashboard_context(
            teacher,
            result["message"]
        )
    )
# =========================
# WEBSOCKET ROUTE
# =========================
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket
):

    await manager.connect(websocket)

    try:

        while True:

            await asyncio.sleep(1)

    except (
        WebSocketDisconnect,
        asyncio.CancelledError
    ):

        manager.disconnect(
            websocket
        )


# =========================
# MARKS ANALYTICS API
# =========================

@app.get("/marks-chart/{student}")
async def marks_chart(student: str):

    data = marks_analytics(student)

    subjects = []
    scores = []

    for item in data:

        subjects.append(item[0])

        scores.append(item[1])

    return {

        "subjects": subjects,

        "scores": scores
    }

# =========================
# ASSIGNMENT ANALYTICS API
# =========================

@app.get("/assignment-chart/{student}")
async def assignment_chart(student: str):

    return assignment_analytics(student)
# =========================
# AI CHATBOT
# =========================

@app.post("/ask-ai")
async def ask_ai_route(

    request: Request,

    message: str = Form(...),

    student: str = Form(...)

):

    # Groq call is blocking/synchronous — run it off the event loop so the
    # server can keep handling other requests while the LLM responds.
    result = await asyncio.to_thread(
        ask_ai,
        message,
        student
    )

    return {

        "response": result
    }
# =========================
# AI PERFORMANCE SUMMARY
# =========================

@app.post("/student-summary")
async def student_summary(

    student: str = Form(...)

):

    result = await asyncio.to_thread(
        generate_student_summary,
        student
    )

    return result
