from http import HTTPStatus

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from ..models import Comment, Follow, Group, Post

User = get_user_model()


class PostPagesTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username='author')
        cls.group = Group.objects.create(
            title='Тестовая группа',
            slug='test-slug',
            description='Тестовое описание',
        )
        small_gif = (
            b'\x47\x49\x46\x38\x39\x61\x02\x00'
            b'\x01\x00\x80\x00\x00\x00\x00\x00'
            b'\xFF\xFF\xFF\x21\xF9\x04\x00\x00'
            b'\x00\x00\x00\x2C\x00\x00\x00\x00'
            b'\x02\x00\x01\x00\x00\x02\x02\x0C'
            b'\x0A\x00\x3B'
        )

        uploaded = SimpleUploadedFile(
            name='small.gif',
            content=small_gif,
            content_type='image/gif'
        )
        cls.post = Post.objects.create(
            author=cls.user,
            text='Тестовый пост',
            group=cls.group,
            image=uploaded
        )

    def setUp(self):
        self.guest_client = Client()
        self.authorized_client = Client()
        self.authorized_client.force_login(self.user)

    def test_views_correct_template(self):
        templates_url_names = {
            reverse('posts:index'): 'posts/index.html',
            reverse('posts:group_list',
                    kwargs={'slug':
                            f'{self.group.slug}'}): 'posts/group_list.html',
            reverse('posts:profile',
                    kwargs={'username':
                            f'{self.user.username}'}): 'posts/profile.html',
            reverse('posts:post_detail',
                    kwargs={'post_id':
                            self.post.id}): 'posts/post_detail.html',
            reverse('posts:post_create'): 'posts/create_post.html',
            reverse('posts:post_edit',
                    kwargs={'post_id':
                            self.post.id}): 'posts/create_post.html'}
        for address, template in templates_url_names.items():
            with self.subTest(address=address):
                response = self.authorized_client.get(address)
                self.assertTemplateUsed(response, template)

    def check_context_contains_page_or_post(self, context, post=False):
        if post:
            self.assertIn('post', context)
            post = context['post']
        else:
            self.assertIn('page_obj', context)
            post = context['page_obj'][0]
        self.assertEqual(post.text, self.post.text)
        self.assertEqual(post.author, self.post.author)
        self.assertEqual(post.group, self.post.group)
        self.assertEqual(post.id, self.post.id)
        self.assertEqual(post.image, self.post.image)

    def test_index_show_correct_context(self):
        response = self.authorized_client.get(reverse('posts:index'))
        self.check_context_contains_page_or_post(response.context)

    def test_group_list_show_correct_context(self):
        response = self.authorized_client.get(
            reverse('posts:group_list', kwargs={'slug': self.group.slug})
        )
        self.check_context_contains_page_or_post(response.context)
        group = response.context['group']
        self.assertEqual(group.description, self.group.description)
        self.assertEqual(group.slug, self.group.slug)

    def test_profile_show_correct_context(self):
        response = self.authorized_client.get(
            reverse('posts:profile',
                    kwargs={'username': self.post.author})
        )
        self.check_context_contains_page_or_post(response.context)
        self.assertEqual(response.context['author'], self.post.author)

    def test_post_detail_show_correct_context(self):
        response = self.authorized_client.get(
            reverse('posts:post_detail', kwargs={'post_id': self.post.id})
        )
        self.check_context_contains_page_or_post(response.context, post=True)

    def test_post_create_page_show_correct_context(self):
        response = self.authorized_client.get(reverse('posts:post_create'))
        form_fields = {
            'text': forms.fields.CharField,
            'group': forms.fields.ChoiceField}
        for value, expected in form_fields.items():
            with self.subTest(value=value):
                form_field = response.context.get('form').fields.get(value)
                self.assertIsInstance(form_field, expected)

    def test_post_appeared_on_the_main_page(self):
        response = self.authorized_client.get(
            reverse('posts:index'))
        self.assertIn(self.post,
                      response.context['page_obj'], 'поста нет на главной')

    def test_post_appeared_on_the_groups_page(self):
        response = self.authorized_client.get(
            reverse('posts:group_list',
                    kwargs={'slug': f'{self.group.slug}'}))
        self.assertIn(self.post,
                      response.context['page_obj'], 'поста нет в группе')

    def test_post_appeared_on_the_profile_page(self):
        response = self.authorized_client.get(
            reverse('posts:profile',
                    kwargs={'username': f'{self.user.username}'}))
        self.assertIn(self.post,
                      response.context['page_obj'], 'поста нет в профиле')

    def test_post_in_right_group(self):
        response = self.authorized_client.get(reverse(
            'posts:group_list',
            kwargs={'slug': f'{self.group.slug}'}))
        self.assertTrue(self.post
                        in response.context['page_obj'])


class PaginatorViewsTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username='author')
        cls.group = Group.objects.create(
            title='Тестовая группа',
            slug='test-slug',
            description='Тестовое описание'
        )
        cls.urls_list = [
            reverse('posts:index'),
            reverse('posts:group_list',
                    kwargs={'slug': cls.group.slug}),
            reverse('posts:profile',
                    kwargs={'username': cls.user.username})
        ]
        post_list = [Post(
            pub_date='01.01.2022',
            text=str(i),
            author=cls.user,
            group=cls.group)
            for i in range(13)]
        Post.objects.bulk_create(post_list)

    def test_first_page_contains_ten_posts(self):
        for url in self.urls_list:
            response = self.client.get(url)
            self.assertEqual(
                len(response.context['page_obj']), settings.MAX_PAGE_AMOUNT
            )

    def test_second_page_contains_three_posts(self):
        for url in self.urls_list:
            response = self.client.get(url + '?page=2')
            self.assertEqual(
                len(response.context['page_obj']), 3
            )


class CommentViewsTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = User.objects.create_user(username='author')
        cls.auth_user = User.objects.create_user(username='auth_user')
        cls.group = Group.objects.create(
            title='Тестовый заголовок',
            description='Описание',
            slug='test-slug'
        )
        cls.post = Post.objects.create(
            author=cls.author,
            text='Тестовый пост',
            pub_date='Дата публикации',
            group=cls.group,
        )

        cls.guest_client = Client()
        cls.authorized_auth = Client()
        cls.authorized_auth.force_login(cls.author)

    def test_add_comment_for_guest(self):
        response = self.guest_client.get(
            reverse(
                'posts:add_comment',
                kwargs={
                    'post_id': self.post.id
                }
            )
        )
        self.assertEqual(
            response.status_code,
            HTTPStatus.FOUND,
            ('Не авторизированный пользователь'
             ' не может оставлять комментарий')
        )

    def test_comment_available(self):
        post = CommentViewsTest.post
        client = self.authorized_auth
        response = client.get(
            reverse(
                'posts:post_detail',
                kwargs={
                    'post_id': post.id
                }
            )
        )
        self.assertEqual(
            response.status_code,
            HTTPStatus.OK,
            ('Авторизированный пользователь'
             ' должен иметь возможность'
             ' оставлять комментарий')
        )
        comments_count = Comment.objects.filter(
            post=post.id
        ).count()
        form_data = {
            'text': 'test_comment',
        }

        response = client.post(
            reverse('posts:post_detail',
                    kwargs={
                        'post_id': post.id
                    }
                    ),
            data=form_data,
            follow=True
        )
        comments = Post.objects.filter(
            id=post.id
        ).values_list('comments', flat=True)
        self.assertEqual(
            comments.count(),
            comments_count + 1)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertFalse(Comment.objects.filter(
            text='test_comment').exists())


class CacheViewsTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = User.objects.create_user(username='author')
        cls.group = Group.objects.create(
            title='Тестовый заголовок',
            description='Описание',
            slug='test-slug'
        )
        cls.post = Post.objects.create(
            author=cls.author,
            text='Тестовый пост',
            pub_date='Дата публикации',
            group=cls.group,
        )

        cls.guest_client = Client()
        cls.authorized_auth = Client()
        cls.authorized_auth.force_login(cls.author)

    def test_cache_index(self):
        response = CacheViewsTest.authorized_auth.get(reverse('posts:index'))
        posts = response.content
        Post.objects.create(
            text='Новый тестовый пост',
            author=CacheViewsTest.author,
        )
        response_old = CacheViewsTest.authorized_auth.get(
            reverse('posts:index')
        )
        old_posts = response_old.content
        self.assertEqual(
            old_posts,
            posts,
            'Не возвращает кэшированную страницу.'
        )
        cache.clear()
        response_new = CacheViewsTest.authorized_auth.get(
            reverse('posts:index')
        )
        new_posts = response_new.content
        self.assertNotEqual(old_posts, new_posts, 'Нет сброса кэша.')


class FollowViewsTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.author = User.objects.create_user(username='author')
        cls.follower = User.objects.create_user(username='follower')
        cls.unfollower = User.objects.create_user(username='unfollower')
        cls.group = Group.objects.create(
            title='Тестовый заголовок',
            description='Описание',
            slug='test-slug'
        )
        cls.post = Post.objects.create(
            author=cls.author,
            text='Тестовый пост',
            pub_date='Дата публикации',
            group=cls.group,
        )
        cls.guest_client = Client()
        cls.authorized_author = Client()
        cls.authorized_author.force_login(cls.author)
        cls.authorized_follower = Client()
        cls.authorized_follower.force_login(cls.follower)
        cls.authorized_unfollower = Client()
        cls.authorized_unfollower.force_login(cls.unfollower)

    def test_follow(self):
        client = FollowViewsTest.authorized_unfollower
        user = FollowViewsTest.unfollower
        author = FollowViewsTest.author
        client.get(
            reverse(
                'posts:profile_follow',
                args=[author.username]
            )
        )
        follower = Follow.objects.filter(
            user=user,
            author=author
        ).exists()
        self.assertTrue(
            follower,
            'Не работает подписка на автора'
        )

    def test_unfollow(self):
        client = FollowViewsTest.authorized_unfollower
        user = FollowViewsTest.unfollower
        author = FollowViewsTest.author
        client.get(
            reverse(
                'posts:profile_unfollow',
                args=[author.username]
            ),

        )
        follower = Follow.objects.filter(
            user=user,
            author=author
        ).exists()
        self.assertFalse(
            follower,
            'Не работает отписка от автора'
        )

    def test_new_author_post_for_follower(self):
        client = FollowViewsTest.authorized_follower
        author = FollowViewsTest.author
        group = FollowViewsTest.group
        client.get(
            reverse(
                'posts:profile_follow',
                args=[author.username]
            )
        )
        response_old = client.get(
            reverse('posts:follow_index')
        )
        old_posts = response_old.context.get(
            'page_obj'
        ).object_list
        self.assertEqual(
            len(response_old.context.get('page_obj').object_list),
            1,
        )
        self.assertIn(
            FollowViewsTest.post,
            old_posts,
        )
        new_post = Post.objects.create(
            text='test_new_post',
            group=group,
            author=author
        )
        cache.clear()
        response_new = client.get(
            reverse('posts:follow_index')
        )
        new_posts = response_new.context.get(
            'page_obj'
        ).object_list
        self.assertEqual(
            len(response_new.context.get('page_obj').object_list),
            2,
        )
        self.assertIn(
            new_post,
            new_posts,
        )

    def test_new_author_post_for_unfollower(self):
        client = FollowViewsTest.authorized_unfollower
        author = FollowViewsTest.author
        group = FollowViewsTest.group
        response_old = client.get(
            reverse('posts:follow_index')
        )
        old_posts = response_old.context.get(
            'page_obj'
        ).object_list
        self.assertEqual(
            len(response_old.context.get('page_obj').object_list),
            0,
        )
        self.assertNotIn(
            FollowViewsTest.post,
            old_posts,
        )
        new_post = Post.objects.create(
            text='test_new_post',
            group=group,
            author=author
        )
        cache.clear()
        response_new = client.get(
            reverse('posts:follow_index')
        )
        new_posts = response_new.context.get(
            'page_obj'
        ).object_list
        self.assertEqual(
            len(response_new.context.get('page_obj').object_list),
            0,
        )
        self.assertNotIn(
            new_post,
            new_posts,
        )
