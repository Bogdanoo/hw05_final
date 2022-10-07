from http import HTTPStatus

from django.test import TestCase


class ViewTestClass(TestCase):
    def test_custom_404_page(self):
        response = self.client.get('/noneexist-page/')
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        self.assertTemplateUsed(response, 'core/404.html')
