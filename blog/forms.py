from django import forms
from django.utils.text import slugify

from .images import MAX_BYTES
from .models import Post


class PostForm(forms.ModelForm):
    slug = forms.SlugField(max_length=80, required=False,
                           help_text="The address: /blog/<slug>/. Leave empty to make one from the title. "
                                     "Fixed once the post has been published.")

    class Meta:
        model = Post
        fields = ["title", "slug", "excerpt", "body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 22}), "excerpt": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.slug_locked:
            self.fields["slug"].disabled = True     # Django keeps the stored value for disabled fields

    def clean_slug(self):
        if self.instance.slug_locked:
            return self.instance.slug
        slug = self.cleaned_data.get("slug") or slugify(self.cleaned_data.get("title") or "")[:70] or "post"
        base, n = slug, 2
        while Post.objects.exclude(pk=self.instance.pk).filter(slug=slug).exists():
            slug, n = f"{base}-{n}"[:80], n + 1
        return slug


class ImageForm(forms.Form):
    file = forms.FileField(help_text=f"JPEG, PNG or WebP, up to {MAX_BYTES // (1024 * 1024)} MB.")
    alt = forms.CharField(max_length=200, label="Alt text",
                          help_text="Describe the image for people who can't see it. Required.")
    make_cover = forms.BooleanField(required=False, label="Use as the cover image")

    def clean_alt(self):
        alt = (self.cleaned_data.get("alt") or "").strip()
        if not alt:
            raise forms.ValidationError("Add alt text.")
        return alt
