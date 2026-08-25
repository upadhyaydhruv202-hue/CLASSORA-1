"""Feature contract for the public student-performance benchmark model."""

from pathlib import Path

TARGET = "Final_Score"

NUMERIC_FEATURES = [
    "Age",
    "Attendance (%)",
    "Midterm_Score",
    "Assignments_Avg",
    "Quizzes_Avg",
    "Participation_Score",
    "Projects_Score",
    "Study_Hours_per_Week",
    "Stress_Level (1-10)",
    "Sleep_Hours_per_Night",
]

CATEGORICAL_FEATURES = [
    "Gender",
    "Department",
    "Extracurricular_Activities",
    "Internet_Access_at_Home",
    "Parent_Education_Level",
    "Family_Income_Level",
]

FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Never used as inputs. Total_Score / Grade are excluded even if they are not
# a simple function of Final_Score on this benchmark.
LEAKAGE_EXCLUDED = ["Total_Score", "Grade", TARGET]

PII_EXCLUDED = ["Student_ID", "First_Name", "Last_Name", "Email"]

DATASET_NAME = "Student Performance & Behavior"
DATASET_SOURCE = "https://github.com/ramyfarouk81/Student-Performance-Behavior"
DATASET_LABEL = "Public/reference student-performance benchmark dataset used for initial model development and validation."
MODEL_VERSION = "perf-final-rf-v1"
MODEL_TYPE = "RandomForestRegressor"
RANDOM_SEED = 42

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "Students_Grading_Dataset.csv"
ARTIFACT_DIR = ROOT / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "final_score_model.joblib"
METADATA_PATH = ARTIFACT_DIR / "metadata.json"
CALIBRATION_MODEL_PATH = ARTIFACT_DIR / "final_score_calibration.joblib"
CALIBRATION_METADATA_PATH = ARTIFACT_DIR / "calibration_metadata.json"
CALIBRATION_VERSION = "perf-final-rf-cal-v1"
CALIBRATION_NAME = "Synthetic demo calibration set"
CALIBRATION_LABEL = (
    "SYNTHETIC calibration data for demo only. Not the public GitHub benchmark. "
    "Not institutional or college-collected student records. Generated so attendance, "
    "assessments, study hours, stress, and sleep can move the estimate."
)
