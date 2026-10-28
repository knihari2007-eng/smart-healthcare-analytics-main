def assess_health_indicators(assessment, age):
    """
    Educational health measurement indicators only.

    These rules do not diagnose disease or calculate
    a clinically validated risk score.
    """

    indicators = []
    warnings = []

    # Validate age
    try:
        age = int(age)

        if age < 1 or age > 120:
            return {
                "assessment_type": "Educational rule-based indicators",
                "is_diagnostic": False,
                "overall_summary": "Invalid age provided.",
                "indicators": [],
                "warnings": ["Age must be between 1 and 120."]
            }

    except (TypeError, ValueError):
        return {
            "assessment_type": "Educational rule-based indicators",
            "is_diagnostic": False,
            "overall_summary": "Age could not be validated.",
            "indicators": [],
            "warnings": ["A valid age is required."]
        }

    # -----------------------------------------
    # 1. BMI ANALYSIS
    # -----------------------------------------
    try:
        bmi = float(assessment["bmi"])

        if not 1 <= bmi <= 100:
            raise ValueError

    except (KeyError, TypeError, ValueError):
        bmi = None
        warnings.append("BMI is missing or invalid.")

    if bmi is not None:

        if age < 20:
            bmi_category = "Requires age-specific assessment"

        elif bmi < 18.5:
            bmi_category = "Underweight range"

        elif bmi < 25:
            bmi_category = "Healthy weight range"

        elif bmi < 30:
            bmi_category = "Overweight range"

        else:
            bmi_category = "Obesity range"

        indicators.append({
            "measurement": "BMI",
            "value": round(bmi, 2),
            "result": bmi_category,
            "explanation": (
                "BMI is a screening measurement, not a diagnosis. "
                "For people under 20, age-specific interpretation "
                "is required."
            )
        })

    # -----------------------------------------
    # 2. BLOOD PRESSURE ANALYSIS
    # -----------------------------------------
    try:
        systolic_bp = int(assessment["systolic_bp"])
        diastolic_bp = int(assessment["diastolic_bp"])

        if not (
            40 <= systolic_bp <= 300
            and 20 <= diastolic_bp <= 200
        ):
            raise ValueError

    except (KeyError, TypeError, ValueError):
        systolic_bp = None
        diastolic_bp = None
        warnings.append(
            "Blood pressure values are missing or invalid."
        )

    if systolic_bp is not None:

        if diastolic_bp >= systolic_bp:
            bp_result = "Measurement requires verification"

            bp_explanation = (
                "The diastolic reading is equal to or higher than "
                "the systolic reading. Verify the entered values "
                "and repeat the measurement if appropriate."
            )

        elif systolic_bp >= 130 or diastolic_bp >= 80:
            bp_result = "Above configured review threshold"

            bp_explanation = (
                "This reading meets the configured educational "
                "reference threshold of 130 systolic or 80 diastolic. "
                "A single reading cannot establish a diagnosis."
            )

        else:
            bp_result = "Below configured review threshold"

            bp_explanation = (
                "This reading is below the configured reference "
                "threshold. This does not by itself establish "
                "that a person is healthy."
            )

        indicators.append({
            "measurement": "Blood pressure",
            "value": (
                str(systolic_bp)
                + "/"
                + str(diastolic_bp)
                + " mmHg"
            ),
            "result": bp_result,
            "explanation": bp_explanation
        })

    # -----------------------------------------
    # 3. GLUCOSE
    # -----------------------------------------
    try:
        glucose = float(assessment["glucose"])

        if not 0 <= glucose <= 2000:
            raise ValueError

    except (KeyError, TypeError, ValueError):
        glucose = None
        warnings.append("Glucose value is missing or invalid.")

    if glucose is not None:
        indicators.append({
            "measurement": "Glucose",
            "value": glucose,
            "result": "Recorded value — interpretation unavailable",
            "explanation": (
                "The glucose unit and testing context, such as "
                "fasting or non-fasting, must be documented before "
                "applying an interpretation rule."
            )
        })

    # -----------------------------------------
    # 4. OVERALL SUMMARY
    # -----------------------------------------
    if not indicators:
        overall_summary = (
            "Insufficient valid measurements for analysis."
        )

    elif warnings:
        overall_summary = (
            "Partial analysis completed. Review the missing "
            "or invalid measurements."
        )

    else:
        overall_summary = (
            "Measurement review completed. Refer to the individual "
            "indicators; this is not a medical diagnosis or a "
            "validated overall risk score."
        )

    # -----------------------------------------
    # 5. RETURN RESULTS
    # -----------------------------------------
    return {
        "assessment_type": "Educational rule-based indicators",
        "is_diagnostic": False,
        "overall_summary": overall_summary,
        "indicators": indicators,
        "warnings": warnings
    }
if __name__ == "__main__":

    sample_assessment = {
        "bmi": 27.5,
        "systolic_bp": 135,
        "diastolic_bp": 85,
        "glucose": 110
    }

    result = assess_health_indicators(
        sample_assessment,
        age=25
    )

    print("Overall Summary:")
    print(result["overall_summary"])

    print("\nHealth Indicators:")

    for indicator in result["indicators"]:
        print("\nMeasurement:", indicator["measurement"])
        print("Value:", indicator["value"])
        print("Result:", indicator["result"])
        print("Explanation:", indicator["explanation"])

    print("\nWarnings:")
    for warning in result["warnings"]:
        print(warning)