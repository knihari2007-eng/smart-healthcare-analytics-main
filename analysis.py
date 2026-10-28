
def calculate_bmi(height_cm, weight_kg):
    height_m = height_cm / 100

    return round(
        weight_kg / (height_m ** 2),
        2
    )


def analyze_assessment(bmi, age):
    if age < 20:
        category = "Requires age-specific BMI assessment"

    elif bmi < 18.5:
        category = "Underweight"

    elif bmi < 25:
        category = "Healthy weight range"

    elif bmi < 30:
        category = "Overweight"

    else:
        category = "Obesity range"

    return {
        "bmi": bmi,
        "interpretation": category,
        "is_diagnostic": False
    }
