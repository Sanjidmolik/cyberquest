"""Client forms for the command center. They save through the existing models."""

from django import forms
from django.core.exceptions import ValidationError

from courses.models import Course
from games.models import Question

_PDF_TYPES = {"application/pdf", "application/x-pdf"}
_MAX_PDF_BYTES = 20 * 1024 * 1024


class CourseManageForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = [
            "code",
            "title",
            "short_description",
            "content",
            "pdf_file",
            "order",
            "is_published",
        ]
        labels = {
            "code": "Course code",
            "title": "Title",
            "short_description": "Short summary",
            "content": "Lesson text",
            "pdf_file": "Learning PDF",
            "order": "Display order",
            "is_published": "Published",
        }
        help_texts = {
            "code": "A short name students can recognize, such as MOD-01.",
            "short_description": "One line shown on the student course list.",
            "content": "Used when no PDF is uploaded. If both exist, students see the PDF.",
            "pdf_file": "Optional PDF. Students page through the file in the reader.",
            "order": "Lower numbers appear first for students.",
            "is_published": "Published courses are visible to students. A draft stays hidden.",
        }
        error_messages = {
            "code": {"unique": "A course with this code already exists."},
        }
        widgets = {
            "content": forms.Textarea(attrs={"rows": 8}),
        }

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if not code:
            raise ValidationError("Enter a course code.")
        return code

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise ValidationError("Enter a course title.")
        return title

    def clean_pdf_file(self):
        uploaded = self.cleaned_data.get("pdf_file")
        if not uploaded:
            return uploaded
        name = (getattr(uploaded, "name", "") or "").lower()
        if not name.endswith(".pdf"):
            raise ValidationError("Upload a PDF file.")
        content_type = getattr(uploaded, "content_type", "") or ""
        if content_type and content_type not in _PDF_TYPES:
            raise ValidationError("Upload a PDF file.")
        size = getattr(uploaded, "size", None)
        if size and size > _MAX_PDF_BYTES:
            raise ValidationError("PDF must be 20 MB or smaller.")
        header = b""
        if hasattr(uploaded, "read"):
            position = uploaded.tell() if hasattr(uploaded, "tell") else 0
            header = uploaded.read(5) or b""
            if hasattr(uploaded, "seek"):
                uploaded.seek(position)
        if header and not header.startswith(b"%PDF"):
            raise ValidationError("That file is not a PDF.")
        return uploaded


class QuestionTextForm(forms.Form):
    """Edits wording on a question that students are not currently receiving."""

    prompt = forms.CharField(label="Question", widget=forms.Textarea(attrs={"rows": 4}))
    option_1 = forms.CharField(label="Answer A", max_length=500)
    option_2 = forms.CharField(label="Answer B", max_length=500)
    option_3 = forms.CharField(label="Answer C", max_length=500, required=False)
    option_4 = forms.CharField(label="Answer D", max_length=500, required=False)
    correct_choice = forms.ChoiceField(
        label="Correct answer",
        choices=(("0", "A"), ("1", "B"), ("2", "C"), ("3", "D")),
    )
    explanation = forms.CharField(label="Explanation", widget=forms.Textarea(attrs={"rows": 3}))
    difficulty = forms.ChoiceField(
        label="Difficulty",
        choices=[("", "Not set")] + list(Question.DIFFICULTY_CHOICES),
        required=False,
    )

    @classmethod
    def from_question(cls, question):
        options = list(question.options or [])
        while len(options) < 4:
            options.append("")
        return cls(initial={
            "prompt": question.prompt,
            "option_1": options[0],
            "option_2": options[1],
            "option_3": options[2],
            "option_4": options[3],
            "correct_choice": str(question.correct_index),
            "explanation": question.explanation,
            "difficulty": question.difficulty or "",
        })

    def apply(self, question):
        options = [
            self.cleaned_data["option_1"].strip(),
            self.cleaned_data["option_2"].strip(),
        ]
        for key in ("option_3", "option_4"):
            value = (self.cleaned_data.get(key) or "").strip()
            if value:
                options.append(value)
        correct = int(self.cleaned_data["correct_choice"])
        if correct >= len(options):
            raise ValidationError("Choose a correct answer that matches one of the answers you entered.")
        question.prompt = self.cleaned_data["prompt"].strip()
        question.options = options
        question.correct_index = correct
        question.explanation = self.cleaned_data["explanation"].strip()
        question.difficulty = self.cleaned_data.get("difficulty") or ""
        question.full_clean()
        question.save()
