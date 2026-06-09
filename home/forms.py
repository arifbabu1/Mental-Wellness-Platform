import re

from django import forms

from .models import AssessmentQuestion, User


CHOICE_BASED_QUESTION_TYPES = {'single_choice', 'multiple_choice', 'likert_scale', 'yes_no'}


class AssessmentQuestionForm(forms.ModelForm):
    class Meta:
        model = AssessmentQuestion
        fields = [
            'category',
            'question_text',
            'question_type',
            'weight_value',
            'track_number',
            'required',
            'is_active',
            'reverse_scoring',
        ]
        widgets = {
            'question_text': forms.Textarea(attrs={'rows': 4}),
            'track_number': forms.NumberInput(attrs={'min': 1}),
            'weight_value': forms.NumberInput(attrs={'min': 1}),
        }


class AssessmentQuestionOptionForm(forms.Form):
    option_text = forms.CharField(max_length=255, required=False)
    score = forms.DecimalField(max_digits=6, decimal_places=2, required=False)

    def clean(self):
        cleaned_data = super().clean()
        option_text = (cleaned_data.get('option_text') or '').strip()
        score = cleaned_data.get('score')
        if option_text and score is None:
            raise forms.ValidationError('Score is required for every option.')
        if score is not None and not option_text:
            raise forms.ValidationError('Option text cannot be blank.')
        cleaned_data['option_text'] = option_text
        return cleaned_data


class CompleteSocialProfileForm(forms.Form):
    phone = forms.CharField(max_length=20, required=True)
    age = forms.IntegerField(min_value=13, max_value=120, required=True)
    gender = forms.ChoiceField(choices=User.GENDER_CHOICES, required=True)
    address = forms.CharField(max_length=255, required=False)

    def clean_phone(self):
        phone = (self.cleaned_data.get('phone') or '').strip()
        normalized = re.sub(r'[\s\-()+]', '', phone)
        if normalized.startswith('88') and len(normalized) == 13:
            normalized = normalized[2:]
        if not re.fullmatch(r'01[3-9]\d{8}', normalized):
            raise forms.ValidationError('Enter a valid Bangladesh mobile number.')
        return normalized
