from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1"])
class PagesNavigationTests(TestCase):
    def test_home_page_loads(self):
        response = self.client.get(reverse("pages:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CyberShield")
        self.assertContains(response, f'href="{reverse("accounts:login")}"')
        self.assertContains(response, f'href="{reverse("accounts:signup")}"')
        self.assertContains(response, f'href="{reverse("courses:intro")}"')
        self.assertContains(response, f'href="{reverse("games:phishing_simulator")}"')
        self.assertContains(response, f'href="{reverse("games:password_cracker")}"')
        self.assertContains(response, f'href="{reverse("games:network_defense")}"')
        self.assertContains(response, f'href="{reverse("games:steganography")}"')
        self.assertContains(response, "Coming Soon")
        self.assertNotContains(response, f'href="{reverse("games:osint")}"')
        self.assertContains(response, f'href="{reverse("certificates:page")}"')
        self.assertContains(response, f'href="{reverse("pages:contact")}"')

    def test_about_page_brand_links_home(self):
        response = self.client.get(reverse("pages:about"))
        self.assertContains(response, f'href="{reverse("pages:home")}"')

    def test_contact_page_brand_links_home(self):
        response = self.client.get(reverse("pages:contact"))
        self.assertContains(response, f'href="{reverse("pages:home")}"')
