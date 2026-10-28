from io import BytesIO
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)
import os
from functools import wraps

from flask import session, redirect, url_for
from werkzeug.security import check_password_hash
from dotenv import load_dotenv




import csv
from io import StringIO
from flask import Response
from report import create_healthcare_report
from risk_analysis import assess_health_indicators
from flask import Flask, request, jsonify, render_template, send_file
import mysql.connector

from db import get_db_connection
from analysis import calculate_bmi, analyze_assessment
from analytics import (
    get_healthcare_analytics,
    create_department_chart,
    create_visits_chart
)
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

if not app.secret_key:
    raise RuntimeError("Set FLASK_SECRET_KEY in your .env file")

from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect(app)
def export_query_as_csv(query, filename):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(query)
        rows = cursor.fetchall()
        headers = [column[0] for column in cursor.description]

        output = StringIO()
        writer = csv.writer(output)

        writer.writerow(headers)

        for row in rows:
            writer.writerow(row)

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition":
                    f"attachment; filename={filename}"
            }
        )

    except mysql.connector.Error:
        app.logger.exception("CSV export failed")
        return jsonify({"error": "Could not export CSV"}), 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        print("SESSION:", dict(session))
        if not session.get("user_id"):
            session.clear()
            return redirect(url_for("login"))

        return view_function(*args, **kwargs)

    return wrapped_view


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        connection = None
        cursor = None

        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)

            cursor.execute(
                """
                SELECT user_id, username, password_hash
                FROM users
                WHERE username = %s
                """,
                (username,)
            )

            user = cursor.fetchone()

            if (
                user is not None
                and check_password_hash(user["password_hash"], password)
            ):
                session.clear()
                session["user_id"] = user["user_id"]
                session["username"] = user["username"]

                return redirect(url_for("home"))

            return render_template(
                "login.html",
                error="Invalid username or password"
            ), 401

        except mysql.connector.Error:
            app.logger.exception("Login database error")

            return render_template(
                "login.html",
                error="Login is temporarily unavailable"
            ), 500

        finally:
            if cursor is not None:
                cursor.close()

            if connection is not None and connection.is_connected():
                connection.close()

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def home():
    return render_template("index.html")

@app.route("/patients")
@login_required
def patients_page():
    return render_template("patients.html")


@app.route("/assessments")
@login_required
def assessment_page():
    return render_template("assessment.html")


@app.route("/visits")
@login_required
def visits_page():
    return render_template("visits.html")


@app.route("/history")
@login_required
def history_page():
    return render_template("history.html")


@app.route("/indicators")
@login_required
def indicators_page():
    return render_template("indicators.html")


@app.route("/api/patients", methods=["GET"])
@login_required
def get_patients():
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT patient_id, name, age, sex, department, created_at
            FROM patients
            ORDER BY patient_id DESC
        """)

        records = cursor.fetchall()

        for record in records:
            if record["created_at"]:
                record["created_at"] = record["created_at"].isoformat()

        return jsonify(records), 200

    except mysql.connector.Error:
        app.logger.exception("Could not retrieve patients")
        return jsonify({"error": "Could not retrieve patients"}), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/api/patients", methods=["POST"])
@login_required
def add_patient():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    sex = str(data.get("sex", "")).strip()
    department = str(data.get("department", "General")).strip()

    try:
        age = int(data.get("age", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Age must be a whole number"}), 400

    if not name or len(name) > 100:
        return jsonify({"error": "Enter a valid patient name"}), 400

    if age < 1 or age > 120:
        return jsonify({"error": "Age must be between 1 and 120"}), 400

    if sex not in ["Male", "Female", "Other"]:
        return jsonify({"error": "Choose a valid sex option"}), 400

    if not department or len(department) > 100:
        return jsonify({"error": "Enter a valid department"}), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("""
            INSERT INTO patients (name, age, sex, department)
            VALUES (%s, %s, %s, %s)
        """, (name, age, sex, department))

        patient_id = cursor.lastrowid
        connection.commit()

        return jsonify({
            "message": "Patient registered successfully",
            "patient_id": patient_id
        }), 201

    except mysql.connector.Error:
        if connection is not None and connection.is_connected():
            connection.rollback()

        app.logger.exception("Patient registration failed")
        return jsonify({"error": "Could not register patient"}), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/api/assessments", methods=["POST"])
@login_required
def add_assessment():
    data = request.get_json(silent=True) or {}

    try:
        patient_id = int(data.get("patient_id"))
        height_cm = float(data.get("height_cm"))
        weight_kg = float(data.get("weight_kg"))
        systolic_bp = int(data.get("systolic_bp"))
        diastolic_bp = int(data.get("diastolic_bp"))
        glucose = float(data.get("glucose"))
    except (TypeError, ValueError):
        return jsonify({
            "error": "Enter valid numeric values for all assessment fields"
        }), 400

    if patient_id < 1:
        return jsonify({"error": "Invalid patient ID"}), 400

    if not (50 <= height_cm <= 250):
        return jsonify({"error": "Height must be between 50 and 250 cm"}), 400

    if not (2 <= weight_kg <= 500):
        return jsonify({"error": "Weight must be between 2 and 500 kg"}), 400

    if not (40 <= systolic_bp <= 300):
        return jsonify({"error": "Systolic BP is outside accepted input limits"}), 400

    if not (20 <= diastolic_bp <= 200):
        return jsonify({"error": "Diastolic BP is outside accepted input limits"}), 400

    if not (0 <= glucose <= 2000):
        return jsonify({"error": "Glucose must be between 0 and 2000; confirm the unit"}), 400

    bmi = calculate_bmi(height_cm, weight_kg)

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT patient_id FROM patients WHERE patient_id = %s",
            (patient_id,)
        )

        if cursor.fetchone() is None:
            return jsonify({"error": "Patient not found"}), 404

        cursor.execute("""
            INSERT INTO assessments (
                patient_id, height_cm, weight_kg,
                systolic_bp, diastolic_bp, glucose, bmi
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            patient_id, height_cm, weight_kg,
            systolic_bp, diastolic_bp, glucose, bmi
        ))

        assessment_id = cursor.lastrowid
        connection.commit()

        return jsonify({
            "message": "Assessment saved successfully",
            "assessment_id": assessment_id,
            "bmi": bmi
        }), 201

    except mysql.connector.Error:
        if connection is not None and connection.is_connected():
            connection.rollback()

        app.logger.exception("Assessment creation failed")
        return jsonify({"error": "Could not save assessment"}), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/api/patients/<int:patient_id>/assessments", methods=["GET"])
@login_required
def patient_assessments(patient_id):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT assessment_id, patient_id, height_cm, weight_kg,
                   systolic_bp, diastolic_bp, glucose, bmi, created_at
            FROM assessments
            WHERE patient_id = %s
            ORDER BY created_at DESC, assessment_id DESC
        """, (patient_id,))

        records = cursor.fetchall()

        for record in records:
            for key in ["height_cm", "weight_kg", "glucose", "bmi"]:
                record[key] = float(record[key])

            record["created_at"] = (
                record["created_at"].isoformat()
                if record["created_at"] else None
            )

        return jsonify(records), 200

    except mysql.connector.Error:
        app.logger.exception("Could not retrieve assessment history")
        return jsonify({"error": "Could not retrieve assessment history"}), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/api/assessments/<int:assessment_id>/analysis", methods=["GET"])
@login_required
def assessment_analysis(assessment_id):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT a.*, p.age
            FROM assessments a
            JOIN patients p ON p.patient_id = a.patient_id
            WHERE a.assessment_id = %s
        """, (assessment_id,))

        record = cursor.fetchone()

        if record is None:
            return jsonify({"error": "Assessment not found"}), 404

        result = analyze_assessment(
            float(record["bmi"]),
            int(record["age"])
        )

        record["bmi"] = float(record["bmi"])
        record["height_cm"] = float(record["height_cm"])
        record["weight_kg"] = float(record["weight_kg"])
        record["glucose"] = float(record["glucose"])
        record["created_at"] = (
            record["created_at"].isoformat()
            if record["created_at"] else None
        )

        return jsonify({
            "assessment": record,
            "analysis": result
        }), 200

    except mysql.connector.Error:
        app.logger.exception("Assessment analysis failed")
        return jsonify({"error": "Could not analyze assessment"}), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/api/visits", methods=["POST"])
@login_required
def add_visit():
    data = request.get_json(silent=True) or {}

    try:
        patient_id = int(data.get("patient_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Enter a valid patient ID"}), 400

    visit_type = str(data.get("visit_type", "Consultation")).strip()
    department = str(data.get("department", "General")).strip()
    notes = str(data.get("notes", "")).strip()

    if patient_id < 1:
        return jsonify({"error": "Invalid patient ID"}), 400

    if not visit_type or len(visit_type) > 50:
        return jsonify({"error": "Enter a valid visit type"}), 400

    if not department or len(department) > 100:
        return jsonify({"error": "Enter a valid department"}), 400

    if len(notes) > 255:
        return jsonify({"error": "Notes must be 255 characters or fewer"}), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            "SELECT patient_id FROM patients WHERE patient_id = %s",
            (patient_id,)
        )

        if cursor.fetchone() is None:
            return jsonify({"error": "Patient not found"}), 404

        cursor.execute("""
            INSERT INTO visits (patient_id, visit_type, department, notes)
            VALUES (%s, %s, %s, %s)
        """, (patient_id, visit_type, department, notes or None))

        visit_id = cursor.lastrowid
        connection.commit()

        return jsonify({
            "message": "Visit recorded successfully",
            "visit_id": visit_id
        }), 201

    except mysql.connector.Error:
        if connection is not None and connection.is_connected():
            connection.rollback()

        app.logger.exception("Visit registration failed")
        return jsonify({"error": "Could not record visit"}), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/api/dashboard/stats", methods=["GET"])
@login_required
def dashboard_stats():
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) AS total_patients FROM patients")
        total_patients = cursor.fetchone()["total_patients"]

        cursor.execute("SELECT COUNT(*) AS total_assessments FROM assessments")
        total_assessments = cursor.fetchone()["total_assessments"]

        cursor.execute("""
            SELECT
                a.assessment_id,
                a.patient_id,
                p.name AS patient_name,
                a.bmi,
                a.created_at
            FROM assessments a
            JOIN patients p ON p.patient_id = a.patient_id
            ORDER BY a.created_at DESC, a.assessment_id DESC
            LIMIT 10
        """)

        recent = cursor.fetchall()

        for record in recent:
            record["bmi"] = float(record["bmi"])
            record["created_at"] = (
                record["created_at"].isoformat()
                if record["created_at"] else None
            )

        return jsonify({
            "total_patients": total_patients,
            "total_assessments": total_assessments,
            "recent_assessments": recent
        }), 200

    except mysql.connector.Error:
        app.logger.exception("Dashboard statistics failed")
        return jsonify({"error": "Could not load dashboard"}), 500

    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/api/analytics", methods=["GET"])
@login_required
def healthcare_analytics():
    connection = None

    try:
        connection = get_db_connection()
        result = get_healthcare_analytics(connection)
        return jsonify(result), 200

    except mysql.connector.Error:
        app.logger.exception("Healthcare analytics failed")
        return jsonify({"error": "Could not load analytics"}), 500

    finally:
        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/api/charts/department", methods=["GET"])
@login_required
def department_chart():
    connection = None

    try:
        connection = get_db_connection()
        image_data = create_department_chart(connection)

        return send_file(
            image_data,
            mimetype="image/png",
            download_name="department_chart.png"
        )

    except mysql.connector.Error:
        app.logger.exception("Department chart failed")
        return jsonify({"error": "Could not generate department chart"}), 500

    finally:
        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/api/charts/visits", methods=["GET"])
@login_required
def visits_chart():
    connection = None

    try:
        connection = get_db_connection()
        image_data = create_visits_chart(connection)

        return send_file(
            image_data,
            mimetype="image/png",
            download_name="visits_chart.png"
        )

    except mysql.connector.Error:
        app.logger.exception("Visits chart failed")
        return jsonify({"error": "Could not generate visits chart"}), 500

    finally:
        if connection is not None and connection.is_connected():
            connection.close()


@app.route(
    "/api/assessments/<int:assessment_id>/indicators",
    methods=["GET"]
)
@login_required
def assessment_indicators(assessment_id):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                a.assessment_id,
                a.patient_id,
                a.bmi,
                a.systolic_bp,
                a.diastolic_bp,
                a.glucose,
                p.age
            FROM assessments a
            JOIN patients p
                ON p.patient_id = a.patient_id
            WHERE a.assessment_id = %s
        """, (assessment_id,))

        assessment = cursor.fetchone()

        if assessment is None:
            return jsonify({
                "error": "Assessment not found"
            }), 404

        # Run the health indicator analysis
        result = assess_health_indicators(
            assessment,
            assessment["age"]
        )

        # Return the complete analysis to the website
        return jsonify({
            "assessment_id": assessment["assessment_id"],
            "patient_id": assessment["patient_id"],
            "analysis": result
        }), 200

    except mysql.connector.Error:
        app.logger.exception("Indicator analysis failed")

        return jsonify({
            "error": "Could not retrieve assessment data"
        }), 500

    except Exception:
        app.logger.exception("Unexpected indicator analysis error")

        return jsonify({
            "error": "Could not complete indicator analysis"
        }), 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/api/reports/healthcare.pdf", methods=["GET"])
@login_required
def download_healthcare_report():
    connection = None
    pdf_buffer = None

    try:
        connection = get_db_connection()
        pdf_buffer = create_healthcare_report(connection)

        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name="healthcare_analytics_report.pdf"
        )

    except mysql.connector.Error:
        app.logger.exception("Report database error")
        return jsonify({
            "error": "Could not retrieve data for the report"
        }), 500

    except Exception:
        app.logger.exception("PDF generation failed")
        return jsonify({
            "error": "Could not generate the PDF report"
        }), 500

    finally:
        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/api/export/patients.csv", methods=["GET"])
@login_required
def export_patients():
    return export_query_as_csv(
        """
        SELECT patient_id, name, age, sex, department, created_at
        FROM patients
        ORDER BY patient_id
        """,
        "patients.csv"
    )


@app.route("/api/export/assessments.csv", methods=["GET"])
@login_required
def export_assessments():
    return export_query_as_csv(
        """
        SELECT assessment_id, patient_id, height_cm, weight_kg,
               systolic_bp, diastolic_bp, glucose, bmi, created_at
        FROM assessments
        ORDER BY assessment_id
        """,
        "assessments.csv"
    )


@app.route("/api/export/visits.csv", methods=["GET"])
@login_required
def export_visits():
    return export_query_as_csv(
        """
        SELECT visit_id, patient_id, visit_date,
               visit_type, department, notes
        FROM visits
        ORDER BY visit_id
        """,
        "visits.csv"
    )

@app.route("/api/patients/<int:patient_id>", methods=["DELETE"])
@login_required
def delete_patient(patient_id):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        connection.start_transaction()
        cursor = connection.cursor()

        # Check whether the patient exists.
        cursor.execute(
            "SELECT patient_id FROM patients WHERE patient_id = %s",
            (patient_id,)
        )

        patient = cursor.fetchone()

        if not patient:
            connection.rollback()
            return jsonify({"error": "Patient not found."}), 404

        # Delete the patient's assessments.
        cursor.execute(
            "DELETE FROM assessments WHERE patient_id = %s",
            (patient_id,)
        )
        deleted_assessments = cursor.rowcount

        # Delete the patient's visits.
        cursor.execute(
            "DELETE FROM visits WHERE patient_id = %s",
            (patient_id,)
        )
        deleted_visits = cursor.rowcount

        # Delete the patient.
        cursor.execute(
            "DELETE FROM patients WHERE patient_id = %s",
            (patient_id,)
        )

        connection.commit()

        return jsonify({
            "message": "Patient and associated records deleted successfully.",
            "patient_id": patient_id,
            "deleted_assessments": deleted_assessments,
            "deleted_visits": deleted_visits
        }), 200

    except Exception:
        if connection:
            connection.rollback()

        app.logger.exception("Failed to delete patient %s", patient_id)

        return jsonify({
            "error": "Unable to delete patient. No changes were committed."
        }), 500

    finally:
        if cursor:
            cursor.close()

        if connection:
            connection.close()

@app.route(
    "/api/reports/patient/<int:patient_id>.pdf",
    methods=["GET"]
)
@login_required
def download_patient_report(patient_id):
    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        # Get the selected patient's details.
        cursor.execute(
            """
            SELECT patient_id, name, age, sex, department, created_at
            FROM patients
            WHERE patient_id = %s
            """,
            (patient_id,)
        )

        patient = cursor.fetchone()

        if patient is None:
            return jsonify({"error": "Patient not found"}), 404

        # Get the latest assessment belonging to this patient.
        cursor.execute(
            """
            SELECT assessment_id, height_cm, weight_kg,
                   systolic_bp, diastolic_bp, glucose, bmi, created_at
            FROM assessments
            WHERE patient_id = %s
            ORDER BY created_at DESC, assessment_id DESC
            LIMIT 1
            """,
            (patient_id,)
        )

        assessment = cursor.fetchone()

        if assessment is None:
            return jsonify({
                "error": "This patient has no health assessment yet."
            }), 404

        # Prepare the PDF.
        pdf_buffer = BytesIO()

        document = SimpleDocTemplate(
            pdf_buffer,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm
        )

        styles = getSampleStyleSheet()
        story = []

        story.append(
            Paragraph(
                "SMART HEALTHCARE",
                styles["Title"]
            )
        )

        story.append(
            Paragraph(
                "Individual Patient Health Assessment Report",
                styles["Heading2"]
            )
        )

        story.append(Spacer(1, 15))

        # Patient information.
        story.append(
            Paragraph("Patient Information", styles["Heading2"])
        )

        patient_data = [
            ["Patient ID", str(patient["patient_id"])],
            ["Patient Name", str(patient["name"])],
            ["Age", str(patient["age"])],
            ["Sex", str(patient["sex"])],
            ["Department", str(patient["department"] or "General")],
            ["Assessment ID", str(assessment["assessment_id"])],
            [
                "Assessment Date",
                str(assessment["created_at"] or "Not available")
            ]
        ]

        patient_table = Table(
            patient_data,
            colWidths=[5 * cm, 11 * cm]
        )

        patient_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF2F8")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#243447")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("PADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP")
            ])
        )

        story.append(patient_table)
        story.append(Spacer(1, 20))

        # Health assessment.
        story.append(
            Paragraph("Health Assessment Results", styles["Heading2"])
        )

        bmi = float(assessment["bmi"])

        if int(patient["age"]) < 20:
            bmi_result = (
                "Age-specific interpretation required; "
                "adult BMI categories are not appropriate."
            )
        elif bmi < 18.5:
            bmi_result = "Below the standard healthy-weight range"
        elif bmi < 25:
            bmi_result = "Healthy weight range"
        elif bmi < 30:
            bmi_result = "Overweight range"
        else:
            bmi_result = "Obesity range"

        systolic = int(assessment["systolic_bp"])
        diastolic = int(assessment["diastolic_bp"])

        # A basic review flag, not a medical diagnosis.
        if diastolic >= systolic:
            bp_result = (
                "Verify measurement: diastolic pressure is not lower "
                "than systolic pressure."
            )
        elif systolic >= 130 or diastolic >= 80:
            bp_result = "Above configured review threshold"
        else:
            bp_result = "Below configured review threshold"

        # The database currently does not store glucose units or
        # fasting/non-fasting context, so do not guess its interpretation.
        glucose_value = assessment["glucose"]
        glucose_result = (
            "Interpretation unavailable: record the glucose unit "
            "and testing context."
        )

        results_data = [
            ["Measurement", "Recorded Value", "Result"],
            [
                "BMI",
                f"{bmi:.2f}",
                bmi_result
            ],
            [
                "Blood Pressure",
                f"{systolic}/{diastolic} mmHg",
                bp_result
            ],
            [
                "Glucose",
                str(glucose_value),
                glucose_result
            ]
        ]

        results_table = Table(
            results_data,
            colWidths=[3.5 * cm, 4 * cm, 8.5 * cm],
            repeatRows=1
        )

        results_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#145374")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("PADDING", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
                    colors.white,
                    colors.HexColor("#F4F8FB")
                ])
            ])
        )

        story.append(results_table)
        story.append(Spacer(1, 20))

        story.append(
            Paragraph("Important Information", styles["Heading2"])
        )

        story.append(
            Paragraph(
                "This report summarizes recorded measurements and "
                "basic screening rules. It is not a medical diagnosis. "
                "Blood pressure readings should be verified when unusual. "
                "Glucose interpretation requires the measurement unit "
                "and testing context. A qualified healthcare professional "
                "should interpret the results.",
                styles["BodyText"]
            )
        )

        story.append(Spacer(1, 15))

        story.append(
            Paragraph(
                "Generated by Smart Healthcare Analysis and "
                "Patient Risk Assessment System",
                styles["Italic"]
            )
        )

        document.build(story)

        pdf_buffer.seek(0)

        safe_patient_id = patient["patient_id"]

        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"patient_{safe_patient_id}_health_report.pdf"
        )

    except mysql.connector.Error:
        app.logger.exception(
            "Database error generating report for patient %s",
            patient_id
        )

        return jsonify({
            "error": "Could not retrieve patient assessment data."
        }), 500

    except Exception:
        app.logger.exception(
            "Could not generate report for patient %s",
            patient_id
        )

        return jsonify({
            "error": "Could not generate the patient report."
        }), 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()


@app.route("/api/patients/by-date", methods=["GET"])
@login_required
def get_patients_by_date():
    selected_date = request.args.get("date", "").strip()

    # Validate the date format
    try:
        search_date = datetime.strptime(
            selected_date, "%Y-%m-%d"
        ).date()

        # Reject invalid or non-standard date formats
        if search_date.isoformat() != selected_date:
            raise ValueError

    except ValueError:
        return jsonify({
            "error": "Please provide a valid date in YYYY-MM-DD format."
        }), 400

    connection = None
    cursor = None

    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                patient_id,
                name,
                age,
                sex,
                department,
                created_at
            FROM patients
            WHERE created_at >= %s
              AND created_at < DATE_ADD(%s, INTERVAL 1 DAY)
            ORDER BY patient_id DESC
        """, (search_date, search_date))

        records = cursor.fetchall()

        for record in records:
            if record["created_at"]:
                record["created_at"] = record["created_at"].isoformat()

        return jsonify(records), 200

    except mysql.connector.Error:
        app.logger.exception("Date-wise patient search failed")

        return jsonify({
            "error": "Could not retrieve patients for the selected date."
        }), 500

    finally:
        if cursor is not None:
            cursor.close()

        if connection is not None and connection.is_connected():
            connection.close()

if __name__ == "__main__":
    app.run(debug=True)
