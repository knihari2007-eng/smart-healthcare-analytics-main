
from io import BytesIO
from datetime import datetime

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
)


def create_healthcare_report(connection):
    buffer = BytesIO()
    cursor = None
    chart_buffer = None
    figure = None

    try:
        cursor = connection.cursor(dictionary=True)

        # Retrieve aggregate statistics.
        cursor.execute("SELECT COUNT(*) AS total FROM patients")
        total_patients = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM assessments")
        total_assessments = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM visits")
        total_visits = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT
                COALESCE(department, 'Unknown') AS department,
                COUNT(*) AS patient_count
            FROM patients
            GROUP BY department
            ORDER BY department
        """)
        department_records = cursor.fetchall()

        cursor.execute("""
            SELECT
                AVG(bmi) AS avg_bmi,
                AVG(systolic_bp) AS avg_systolic,
                AVG(diastolic_bp) AS avg_diastolic,
                AVG(glucose) AS avg_glucose
            FROM assessments
        """)
        averages = cursor.fetchone()

        # Create a Matplotlib chart.
        departments = []
        patient_counts = []

        for record in department_records:
            departments.append(record["department"])
            patient_counts.append(int(record["patient_count"]))

        figure, axis = plt.subplots(figsize=(7, 3.5))

        if departments:
            axis.bar(departments, patient_counts)
            axis.set_title("Patients by Department")
            axis.set_xlabel("Department")
            axis.set_ylabel("Patient Count")
            axis.tick_params(axis="x", rotation=25)
        else:
            axis.text(
                0.5, 0.5, "No patient data available",
                ha="center", va="center"
            )
            axis.set_axis_off()

        figure.tight_layout()

        chart_buffer = BytesIO()
        figure.savefig(
            chart_buffer,
            format="png",
            dpi=130,
            bbox_inches="tight"
        )
        chart_buffer.seek(0)

        # Create the PDF.
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.7 * cm,
            leftMargin=1.7 * cm,
            topMargin=1.5 * cm,
            bottomMargin=1.5 * cm
        )

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            textColor=colors.HexColor("#1D4ED8")
        ))

        story = []

        story.append(Paragraph(
            "Healthcare Analytics Report",
            styles["ReportTitle"]
        ))

        story.append(Paragraph(
            "Generated on: " + datetime.now().strftime(
                "%d %B %Y, %H:%M"
            ),
            styles["Normal"]
        ))

        story.append(Spacer(1, 0.4 * cm))

        story.append(Paragraph(
            "1. System Summary",
            styles["Heading2"]
        ))

        summary_data = [
            ["Metric", "Total"],
            ["Registered patients", str(total_patients)],
            ["Recorded assessments", str(total_assessments)],
            ["Recorded visits", str(total_visits)]
        ]

        summary_table = Table(
            summary_data,
            colWidths=[9 * cm, 5 * cm]
        )

        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0),
             colors.HexColor("#DBEAFE")),
            ("TEXTCOLOR", (0, 0), (-1, 0),
             colors.HexColor("#1E3A8A")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("PADDING", (0, 0), (-1, -1), 7),
            ("ALIGN", (1, 1), (1, -1), "CENTER")
        ]))

        story.append(summary_table)
        story.append(Spacer(1, 0.5 * cm))

        story.append(Paragraph(
            "2. Patients by Department",
            styles["Heading2"]
        ))

        for record in department_records:
            story.append(Paragraph(
                "{}: {} patients".format(
                    record["department"],
                    record["patient_count"]
                ),
                styles["Normal"]
            ))

        story.append(Spacer(1, 0.3 * cm))

        chart_image = Image(
            chart_buffer,
            width=16 * cm,
            height=8 * cm
        )

        story.append(chart_image)
        story.append(Spacer(1, 0.3 * cm))

        story.append(Paragraph(
            "3. Average Recorded Measurements",
            styles["Heading2"]
        ))

        def format_average(value):
            if value is None:
                return "No data"
            return "{:.2f}".format(float(value))

        average_data = [
            ["Measurement", "Average"],
            ["BMI (kg/m²)", format_average(averages["avg_bmi"])],
            ["Systolic BP (mmHg)",
             format_average(averages["avg_systolic"])],
            ["Diastolic BP (mmHg)",
             format_average(averages["avg_diastolic"])],
            ["Glucose (unit not specified)",
             format_average(averages["avg_glucose"])]
        ]

        average_table = Table(
            average_data,
            colWidths=[9 * cm, 5 * cm]
        )

        average_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0),
             colors.HexColor("#DBEAFE")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("PADDING", (0, 0), (-1, -1), 7)
        ]))

        story.append(average_table)
        story.append(Spacer(1, 0.5 * cm))

        story.append(Paragraph(
            "Limitations and intended use",
            styles["Heading2"]
        ))

        story.append(Paragraph(
            "This report provides descriptive statistics for an "
            "educational software project. Averages and BMI "
            "categories are not diagnoses or validated predictions "
            "of disease. Glucose interpretation requires documented "
            "units and measurement context. Use synthetic or "
            "de-identified data for demonstrations.",
            styles["Normal"]
        ))

        document.build(story)
        buffer.seek(0)

        return buffer

    finally:
        if cursor is not None:
            cursor.close()

        if figure is not None:
            plt.close(figure)

        if chart_buffer is not None:
            chart_buffer.close()
