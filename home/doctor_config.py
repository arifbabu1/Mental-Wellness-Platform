DOCTOR_SPECIALIZATION_CHOICES = [
    ('Psychiatrist', 'Psychiatrist'),
    ('Clinical Psychologist', 'Clinical Psychologist'),
    ('Therapist', 'Therapist'),
    ('Counselor', 'Counselor'),
    ('Child Psychiatrist', 'Child Psychiatrist'),
    ('Child Psychologist', 'Child Psychologist'),
    ('Geriatric Psychologist', 'Geriatric Psychologist'),
    ('Addiction Specialist', 'Addiction Specialist'),
    ('Marriage and Family Therapist', 'Marriage and Family Therapist'),
    ('Neuropsychiatrist', 'Neuropsychiatrist'),
    ('Neuropsychologist', 'Neuropsychologist'),
]

DOCTOR_PRIMARY_FOCUS_CHOICES = [
    ('Depression', 'Depression'),
    ('Anxiety', 'Anxiety'),
    ('Stress', 'Stress'),
    ('Sleep', 'Sleep'),
    ('Schizophrenia', 'Schizophrenia'),
    ('OCD', 'OCD'),
    ('Neurological Disorders', 'Neurological Disorders'),
    ('Talk Therapy', 'Talk Therapy'),
    ('Emotional Healing', 'Emotional Healing'),
    ('Substance Abuse', 'Substance Abuse'),
    ('Alcohol Addiction', 'Alcohol Addiction'),
    ('Recovery Programs', 'Recovery Programs'),
]

DEFAULT_PRIMARY_FOCUS = 'Stress'

DOCTOR_SPECIALIZATION_VALUES = {value for value, _label in DOCTOR_SPECIALIZATION_CHOICES}
DOCTOR_PRIMARY_FOCUS_VALUES = {value for value, _label in DOCTOR_PRIMARY_FOCUS_CHOICES}
