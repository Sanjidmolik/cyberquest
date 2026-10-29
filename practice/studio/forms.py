from django import forms

from courses.models import Course

from ..models import Scenario
from .services import MAX_IMPORT_BYTES


def _topics():
    return Course.objects.order_by("order", "title")


class TopicField(forms.ModelChoiceField):
    def label_from_instance(self, course):
        return f"{course.title} ({course.code})"


class ListFilterForm(forms.Form):
    q = forms.CharField(required=False, max_length=100)
    topic = TopicField(queryset=Course.objects.none(), required=False, empty_label="All topics",
                       widget=forms.Select(attrs={"aria-label": "Topic"}))
    kind = forms.ChoiceField(required=False, choices=[("", "All kinds")] + Scenario.KIND,
                             widget=forms.Select(attrs={"aria-label": "Kind"}))
    status = forms.ChoiceField(required=False, choices=[("", "All statuses")] + Scenario.STATUS,
                               widget=forms.Select(attrs={"aria-label": "Status"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["topic"].queryset = _topics()


class TemplateStartForm(forms.Form):
    topic = TopicField(queryset=Course.objects.none(), empty_label="Choose a topic",
                       help_text="The course this session practises. You can change it later.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["topic"].queryset = _topics()


class ImportForm(forms.Form):
    file = forms.FileField(help_text="A .json file exported from the Practice Studio of a CyberQuest site.")
    topic = TopicField(queryset=Course.objects.none(), required=False, empty_label="Use the topic in the file",
                       help_text="Choose one if the file's topic doesn't exist on this site.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["topic"].queryset = _topics()

    def clean_file(self):
        upload = self.cleaned_data["file"]
        if not upload.name.lower().endswith(".json"):
            raise forms.ValidationError("Choose a .json file.")
        if upload.size > MAX_IMPORT_BYTES:
            raise forms.ValidationError(f"The file is larger than {MAX_IMPORT_BYTES // 1024} KB.")
        return upload
