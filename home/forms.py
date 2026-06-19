import re

from django import forms

from .models import AssessmentQuestion, User


CHOICE_BASED_QUESTION_TYPES = {'single_choice', 'multiple_choice', 'likert_scale', 'yes_no'}


class AssessmentQuestionForm(forms.ModelForm):
    QUESTION_GROUP_CHOICES = (
        ('general', 'General screening question'),
        ('dynamic', 'Dynamic/follow-up question'),
    )

    question_group = forms.ChoiceField(
        choices=QUESTION_GROUP_CHOICES,
        initial='general',
        required=False,
        help_text='General questions are the first seven screening questions. Dynamic/follow-up questions are managed separately from the patient scoring engine.',
    )

    class Meta:
        model = AssessmentQuestion
        fields = [
            'question_group',
            'category',
            'question_text',
            'question_text_bn',
            'question_type',
            'weight_value',
            'track_number',
            'is_core',
            'core_order',
            'is_required',
            'option_choices_bn',
            'required',
            'is_active',
            'reverse_scoring',
        ]
        widgets = {
            'question_text': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Write the patient-facing question text...'}),
            'question_text_bn': forms.Textarea(attrs={'rows': 4, 'placeholder': 'বাংলা অনুবাদ লিখুন (optional)'}),
            'option_choices_bn': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Optional JSON for Bangla option labels'}),
            'track_number': forms.NumberInput(attrs={'min': 1}),
            'core_order': forms.NumberInput(attrs={'min': 1, 'max': 7}),
            'weight_value': forms.NumberInput(attrs={'min': 1}),
        }
        labels = {
            'track_number': 'Order / serial number',
            'weight_value': 'Question weight',
            'is_active': 'Active',
            'is_core': 'Protected core question',
            'core_order': 'Core order',
            'is_required': 'System required',
            'question_text_bn': 'Bangla question text',
            'option_choices_bn': 'Bangla option choices',
        }
        help_texts = {
            'category': 'Used by the existing scoring and doctor recommendation logic.',
            'weight_value': 'Patient score uses selected option value multiplied by this weight.',
            'track_number': 'The first seven general screening questions should be ordered 1-7.',
            'is_core': 'Core questions are protected from deletion and deactivation.',
            'core_order': 'Core questions must use exactly one order from 1 to 7.',
            'is_required': 'Core questions are always system-required.',
            'reverse_scoring': 'Use only if lower answer values should count as higher risk for this question.',
            'question_text_bn': 'Optional Bangla translation. Leave blank to fall back to English.',
            'option_choices_bn': 'Optional Bangla option labels as JSON list. Leave blank to fall back to translated defaults.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = getattr(self, 'instance', None)
        if instance and instance.pk and instance.track_number > 7:
            self.fields['question_group'].initial = 'dynamic'
        if instance and instance.pk and instance.is_core:
            self.fields['question_group'].initial = 'general'
            self.fields['is_core'].disabled = True
            self.fields['core_order'].disabled = True
            self.fields['is_required'].disabled = True
        for field in self.fields.values():
            widget = field.widget
            existing_class = widget.attrs.get('class', '')
            widget.attrs['class'] = f'{existing_class} form-control'.strip()

    def clean_question_text(self):
        question_text = (self.cleaned_data.get('question_text') or '').strip()
        if not question_text:
            raise forms.ValidationError('Question text is required.')
        return question_text

    def clean(self):
        cleaned_data = super().clean()
        question_group = cleaned_data.get('question_group')
        track_number = cleaned_data.get('track_number')
        is_core = cleaned_data.get('is_core')
        core_order = cleaned_data.get('core_order')
        if not question_group:
            question_group = 'dynamic' if track_number and track_number > 7 else 'general'
            cleaned_data['question_group'] = question_group

        if is_core:
            question_group = 'general'
            cleaned_data['question_group'] = question_group
            cleaned_data['is_active'] = True
            cleaned_data['required'] = True
            cleaned_data['is_required'] = True
            if core_order is None and track_number:
                cleaned_data['core_order'] = track_number
                core_order = track_number
            if core_order not in range(1, 8):
                self.add_error('core_order', 'Core assessment question order must be between 1 and 7.')
            elif track_number and track_number != core_order:
                self.add_error('track_number', 'Core question order and display order must match.')

        if track_number is not None and track_number < 1:
            self.add_error('track_number', 'Order number must be 1 or higher.')

        if question_group == 'general' and track_number and track_number > 7:
            self.add_error('track_number', 'General screening questions should use order numbers 1-7.')
        if question_group == 'dynamic' and track_number and track_number <= 7:
            self.add_error('track_number', 'Dynamic/follow-up questions should use order number 8 or higher so they do not replace the first seven screening questions.')

        return cleaned_data


class AssessmentQuestionOptionForm(forms.Form):
    option_order = forms.IntegerField(min_value=1, required=False)
    option_text = forms.CharField(max_length=255, required=False)
    score = forms.DecimalField(max_digits=6, decimal_places=2, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['option_order'].widget.attrs.update({'class': 'form-control option-order-input', 'min': '1'})
        self.fields['option_text'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Never, Rarely, Sometimes...'})
        self.fields['score'].widget.attrs.update({'class': 'form-control', 'step': '0.01', 'placeholder': '0'})

    def clean(self):
        cleaned_data = super().clean()
        option_order = cleaned_data.get('option_order')
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
