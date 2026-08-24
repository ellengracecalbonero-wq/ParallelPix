from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    send_from_directory
)

import mysql.connector
from flask_bcrypt import Bcrypt
from config import DB_CONFIG

from PIL import Image, ImageFilter, ImageFile

from concurrent.futures import ThreadPoolExecutor

from werkzeug.utils import secure_filename

import os
import time


# ==================================================
# FLASK CONFIGURATION
# ==================================================

app = Flask(__name__)

app.secret_key = "parallelpix_secret_key"

bcrypt = Bcrypt(app)

ImageFile.LOAD_TRUNCATED_IMAGES = True


# ==================================================
# FOLDERS
# ==================================================

UPLOAD_FOLDER = "uploads"
PROCESSED_FOLDER = "processed"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PROCESSED_FOLDER, exist_ok=True)


# ==================================================
# DATABASE
# ==================================================

def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


# ==================================================
# HOME
# ==================================================

@app.route("/")
def index():

    return render_template(
        "index.html"
    )


# ==================================================
# REGISTER
# ==================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        fullname = request.form["fullname"]
        email = request.form["email"]
        username = request.form["username"]
        password = request.form["password"]

        hashed_password = bcrypt.generate_password_hash(
            password
        ).decode("utf-8")

        try:

            connection = get_db_connection()

            cursor = connection.cursor()

            query = """
                INSERT INTO users
                (fullname, email, username, password)
                VALUES (%s, %s, %s, %s)
            """

            cursor.execute(
                query,
                (
                    fullname,
                    email,
                    username,
                    hashed_password
                )
            )

            connection.commit()

            cursor.close()
            connection.close()

            flash(
                "Registration successful! You can now log in.",
                "success"
            )

            return redirect(
                url_for("login")
            )

        except mysql.connector.Error as error:

            return f"Database error: {error}"

    return render_template(
        "register.html"
    )


# ==================================================
# LOGIN
# ==================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        try:

            connection = get_db_connection()

            cursor = connection.cursor(
                dictionary=True
            )

            cursor.execute(
                """
                SELECT *
                FROM users
                WHERE username = %s
                """,
                (username,)
            )

            user = cursor.fetchone()

            cursor.close()
            connection.close()

            if user and bcrypt.check_password_hash(
                user["password"],
                password
            ):

                session["user_id"] = user["id"]

                session["username"] = user["username"]

                session["fullname"] = user["fullname"]

                return redirect(
                    url_for("dashboard")
                )

            else:

                flash(
                    "Invalid username or password.",
                    "error"
                )

        except mysql.connector.Error as error:

            return f"Database error: {error}"

    return render_template(
        "login.html"
    )


# ==================================================
# DASHBOARD
# ==================================================

@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    return render_template(
        "dashboard.html",

        fullname=session["fullname"],

        username=session["username"]
    )


# ==================================================
# LOGOUT
# ==================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# ==================================================
# IMAGE PROCESSING FUNCTIONS
# ==================================================

def resize_image(image):

    image = image.copy()

    image.thumbnail(
        (800, 800)
    )

    return image


def grayscale_image(image):

    return image.convert("L")


def reduce_noise(image):

    return image.filter(
        ImageFilter.MedianFilter(
            size=3
        )
    )


# ==================================================
# SEQUENTIAL PROCESSING
# ==================================================

def sequential_processing(image):

    start_time = time.perf_counter()

    resized = resize_image(image)

    grayscale = grayscale_image(image)

    noise_reduced = reduce_noise(image)

    end_time = time.perf_counter()

    processing_time = (
        end_time - start_time
    )

    return (
        resized,
        grayscale,
        noise_reduced,
        processing_time
    )


# ==================================================
# PARALLEL PROCESSING
# ==================================================

def parallel_processing(image):

    start_time = time.perf_counter()

    with ThreadPoolExecutor(
        max_workers=3
    ) as executor:

        resize_task = executor.submit(
            resize_image,
            image
        )

        grayscale_task = executor.submit(
            grayscale_image,
            image
        )

        noise_task = executor.submit(
            reduce_noise,
            image
        )

        resized = resize_task.result()

        grayscale = grayscale_task.result()

        noise_reduced = noise_task.result()

    end_time = time.perf_counter()

    processing_time = (
        end_time - start_time
    )

    return (
        resized,
        grayscale,
        noise_reduced,
        processing_time
    )


# ==================================================
# PROCESS IMAGE
# ==================================================

@app.route(
    "/process",
    methods=["POST"]
)
def process():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )


    if "image" not in request.files:

        flash(
            "No image selected.",
            "error"
        )

        return redirect(
            url_for("dashboard")
        )


    file = request.files["image"]


    if file.filename == "":

        flash(
            "Please select an image.",
            "error"
        )

        return redirect(
            url_for("dashboard")
        )


    filename = secure_filename(
        file.filename
    )


    allowed_extensions = {
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".gif",
        ".webp"
    }


    extension = os.path.splitext(
        filename
    )[1].lower()


    if extension not in allowed_extensions:

        return (
            "Invalid image format. "
            "Please upload JPG, JPEG, PNG, BMP, GIF, or WEBP."
        )


    # ==================================================
    # SAVE IMAGE
    # ==================================================

    upload_path = os.path.join(
        UPLOAD_FOLDER,
        filename
    )

    file.save(
        upload_path
    )


    # ==================================================
    # VERIFY IMAGE
    # ==================================================

    try:

        with Image.open(
            upload_path
        ) as test_image:

            test_image.verify()

    except Exception:

        return (
            "The uploaded file is not a valid "
            "or complete image. Please choose another image."
        )


    # ==================================================
    # OPEN IMAGE
    # ==================================================

    try:

        image = Image.open(
            upload_path
        )

        image.load()


        if image.mode not in (
            "RGB",
            "RGBA"
        ):

            image = image.convert(
                "RGB"
            )


        # ==================================================
        # SEQUENTIAL
        # ==================================================

        (
            seq_resized,
            seq_grayscale,
            seq_noise,
            sequential_time
        ) = sequential_processing(
            image
        )


        # ==================================================
        # PARALLEL
        # ==================================================

        (
            resized,
            grayscale,
            noise_reduced,
            parallel_time
        ) = parallel_processing(
            image
        )


        # ==================================================
        # PERFORMANCE
        # ==================================================

        if parallel_time > 0:

            speedup = (
                sequential_time /
                parallel_time
            )

        else:

            speedup = 0


        workers = 3


        efficiency = (
            speedup /
            workers
        ) * 100


        # ==================================================
        # OUTPUT FILENAMES
        # ==================================================

        name, extension = os.path.splitext(
            filename
        )


        resized_filename = (
            name +
            "_resized" +
            extension
        )


        grayscale_filename = (
            name +
            "_grayscale.png"
        )


        noise_filename = (
            name +
            "_noise_reduced" +
            extension
        )


        # ==================================================
        # OUTPUT PATHS
        # ==================================================

        resized_path = os.path.join(
            PROCESSED_FOLDER,
            resized_filename
        )


        grayscale_path = os.path.join(
            PROCESSED_FOLDER,
            grayscale_filename
        )


        noise_path = os.path.join(
            PROCESSED_FOLDER,
            noise_filename
        )


        # ==================================================
        # SAVE RESULTS
        # ==================================================

        resized.save(
            resized_path
        )

        grayscale.save(
            grayscale_path
        )

        noise_reduced.save(
            noise_path
        )


        # ==================================================
        # PERFORMANCE INTERPRETATION
        # ==================================================

        if speedup > 1:

            interpretation = (
                "Parallel processing was faster for this "
                "particular image and workload. The system "
                f"achieved a speedup of {speedup:.2f}× using "
                f"{workers} workers."
            )

        elif speedup < 1:

            interpretation = (
                "Sequential processing was faster for this "
                "particular image and workload. This can "
                "happen when the processing workload is small "
                "or when parallel overhead is significant."
            )

        else:

            interpretation = (
                "Sequential and parallel processing produced "
                "nearly the same execution time for this workload."
            )


        # ==================================================
        # RESULTS PAGE
        # ==================================================

        return render_template(

            "results.html",

            original=filename,

            resized=resized_filename,

            grayscale=grayscale_filename,

            noise_reduced=noise_filename,

            sequential_time=sequential_time,

            parallel_time=parallel_time,

            speedup=speedup,

            efficiency=efficiency,

            workers=workers,

            interpretation=interpretation
        )


    except Exception as error:

        return (
            f"Image processing error: {error}"
        )


# ==================================================
# SERVE UPLOADED IMAGES
# ==================================================

@app.route(
    "/uploads/<filename>"
)
def uploaded_file(filename):

    return send_from_directory(
        UPLOAD_FOLDER,
        filename
    )


# ==================================================
# SERVE PROCESSED IMAGES
# ==================================================

@app.route(
    "/processed/<filename>"
)
def processed_file(filename):

    return send_from_directory(
        PROCESSED_FOLDER,
        filename
    )


# ==================================================
# RUN APPLICATION
# ==================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )