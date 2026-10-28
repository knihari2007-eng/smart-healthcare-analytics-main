
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from io import BytesIO


def get_healthcare_analytics(connection):
    cursor = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT patient_id, age, department
            FROM patients
        """)
        patient_records = cursor.fetchall()

        cursor.execute("""
            SELECT visit_id, patient_id, visit_date,
                   visit_type, department
            FROM visits
        """)
        visit_records = cursor.fetchall()

        cursor.execute("""
            SELECT assessment_id, patient_id, bmi,
                   systolic_bp, diastolic_bp, glucose
            FROM assessments
        """)
        assessment_records = cursor.fetchall()

        patients = pd.DataFrame(patient_records)
        visits = pd.DataFrame(visit_records)
        assessments = pd.DataFrame(assessment_records)

        department_counts = {}

        if not patients.empty:
            patients["department"] = (
                patients["department"].fillna("Unknown")
            )

            department_counts = {
                str(key): int(value)
                for key, value in
                patients.groupby("department").size().items()
            }

        visits_by_date = {}

        if not visits.empty:
            visits["visit_date"] = pd.to_datetime(
                visits["visit_date"], errors="coerce"
            )

            visits = visits.dropna(subset=["visit_date"])
            visits["date"] = visits["visit_date"].dt.strftime(
                "%Y-%m-%d"
            )

            visits_by_date = {
                str(key): int(value)
                for key, value in
                visits.groupby("date").size().items()
            }

        measurement_averages = {
            "bmi": None,
            "systolic_bp": None,
            "diastolic_bp": None,
            "glucose": None
        }

        if not assessments.empty:
            columns = list(measurement_averages.keys())

            for column in columns:
                values = pd.to_numeric(
                    assessments[column], errors="coerce"
                )

                values = values.replace(
                    [np.inf, -np.inf], np.nan
                ).dropna()

                if not values.empty:
                    measurement_averages[column] = round(
                        float(values.mean()), 2
                    )

        return {
            "total_patients": int(len(patients)),
            "total_visits": int(len(visit_records)),
            "total_assessments": int(len(assessment_records)),
            "patients_by_department": department_counts,
            "visits_by_date": visits_by_date,
            "measurement_averages": measurement_averages
        }

    finally:
        if cursor is not None:
            cursor.close()


def create_department_chart(connection):
    cursor = None
    fig = None

    try:
        cursor = connection.cursor(dictionary=True)

        cursor.execute("""
            SELECT COALESCE(department, 'Unknown') AS department,
                   COUNT(*) AS patient_count
            FROM patients
            GROUP BY department
            ORDER BY department
        """)

        records = cursor.fetchall()

        departments = []
        counts = []

        for record in records:
            departments.append(record["department"])
            counts.append(int(record["patient_count"]))

        fig, ax = plt.subplots(figsize=(8, 5))

        if departments:
            ax.bar(departments, counts)
            ax.set_xlabel("Department")
            ax.set_ylabel("Number of Patients")
            ax.set_title("Patients by Department")
            ax.tick_params(axis="x", rotation=30)
        else:
            ax.text(
                0.5, 0.5, "No patient data available",
                ha="center", va="center"
            )
            ax.set_axis_off()

        fig.tight_layout()

        image_data = BytesIO()
        fig.savefig(image_data, format="png", dpi=100)
        image_data.seek(0)

        return image_data

    finally:
        if fig is not None:
            plt.close(fig)

        if cursor is not None:
            cursor.close()



def create_visits_chart(connection):
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import pandas as pd
    from io import BytesIO

    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT DATE(visit_date) AS visit_date,
                   COUNT(*) AS total_visits
            FROM visits
            GROUP BY DATE(visit_date)
            ORDER BY DATE(visit_date)
        """)

        rows = cursor.fetchall()

        fig, ax = plt.subplots(figsize=(10, 5))

        if rows:
            df = pd.DataFrame(
                rows,
                columns=["visit_date", "total_visits"]
            )

            df["visit_date"] = pd.to_datetime(df["visit_date"])

            ax.plot(
                df["visit_date"],
                df["total_visits"],
                marker="o",
                linestyle="-",
                linewidth=2
            )

            ax.set_ylim(bottom=0)
            ax.xaxis.set_major_formatter(
                mdates.DateFormatter("%d %b %Y")
            )

            if len(df) == 1:
                visit_date = df["visit_date"].iloc[0]
                ax.set_xlim(
                    visit_date - pd.Timedelta(days=2),
                    visit_date + pd.Timedelta(days=2)
                )
            else:
                ax.margins(x=0.1)

            fig.autofmt_xdate()

        else:
            ax.text(
                0.5, 0.5,
                "No visit data available",
                ha="center",
                va="center",
                transform=ax.transAxes
            )

        ax.set_title("Visits Over Time")
        ax.set_xlabel("Visit Date")
        ax.set_ylabel("Number of Visits")
        ax.grid(True, linestyle="--", alpha=0.4)

        fig.tight_layout()

        image_buffer = BytesIO()
        fig.savefig(image_buffer, format="png", dpi=120)
        image_buffer.seek(0)

        return image_buffer

    finally:
        cursor.close()
        plt.close(fig)
