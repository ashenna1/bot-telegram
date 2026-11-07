import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendPhoto

from bot import db
from bot.handlers import user
from bot.keyboards.inline import after_video_kb
from bot.utils import downloader


class CoverTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)
        self.db_patch = patch.object(db, 'DATABASE_PATH', self.path / 'bot.db')
        self.db_patch.start()
        await db.init_db()
        user._active_cover_users.clear()

    async def asyncTearDown(self):
        self.db_patch.stop()
        self.tmp.cleanup()

    async def test_persistence_and_keyboard(self):
        token = 'a' * 32
        await db.save_video_cover(token, 123, 'https://www.youtube.com/watch?v=abc', 'youtube')
        await db.init_db()  # reopening an existing database does not lose buttons
        self.assertEqual(await db.get_video_cover(token), (123, 'https://www.youtube.com/watch?v=abc', 'youtube'))
        kb = after_video_kb('youtube', 'https://www.youtube.com/watch?v=abc', token)
        self.assertIn('cover:' + token, [b.callback_data for row in kb.inline_keyboard for b in row])
        self.assertLessEqual(len(('cover:' + token).encode()), 64)
        await db.delete_video_cover(token)
        self.assertIsNone(await db.get_video_cover(token))

    async def test_download_cover_invokes_ytdlp_and_cookies(self):
        proc = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b'', b'')))
        (self.path / 'cover.webp').write_bytes(b'original-webp-image')
        with patch.object(downloader, '_base_opts', return_value=['--cookies', 'cookies.txt']), patch.object(downloader.asyncio, 'create_subprocess_exec', AsyncMock(return_value=proc)) as run:
            path = await downloader.download_cover('https://example.com/post', 'instagram', self.path)
        self.assertEqual(path, self.path / 'cover.webp')
        self.assertEqual(path.read_bytes(), b'original-webp-image')
        args = run.await_args.args
        self.assertIn('--write-thumbnail', args)
        self.assertIn('--skip-download', args)
        self.assertNotIn('--convert-thumbnails', args)
        self.assertIn('--cookies', args)
        self.assertEqual(args[-2:], ('--', 'https://example.com/post'))

    async def test_download_missing_or_failed(self):
        proc = SimpleNamespace(returncode=0, communicate=AsyncMock(return_value=(b'', b'')))
        with patch.object(downloader, '_base_opts', return_value=[]), patch.object(downloader.asyncio, 'create_subprocess_exec', AsyncMock(return_value=proc)):
            self.assertIsNone(await downloader.download_cover('https://example.com', 'youtube', self.path))
            proc.returncode = 1
            with self.assertRaises(RuntimeError):
                await downloader.download_cover('https://example.com', 'youtube', self.path)

    def callback(self, chat_id=123):
        return SimpleNamespace(data='cover:token', message=SimpleNamespace(chat=SimpleNamespace(id=chat_id)),
                               from_user=SimpleNamespace(id=7), answer=AsyncMock())

    async def test_callback_sends_original_as_document_and_cleans_up(self):
        await db.save_video_cover('token', 123, 'https://instagram.com/p/x', 'instagram')
        callback = self.callback()
        delivered = {}
        async def send_document(*, chat_id, document, caption):
            delivered.update(chat_id=chat_id, filename=document.filename,
                             data=Path(document.path).read_bytes(), caption=caption)
            return SimpleNamespace(message_id=9)
        bot = SimpleNamespace(send_photo=AsyncMock(), send_document=AsyncMock(side_effect=send_document), send_message=AsyncMock())
        async def fetch(url, platform, workdir):
            p = workdir / 'cover.webp'
            p.write_bytes(b'original-webp-image')
            return p
        with patch('bot.config.TMP_DIR', self.path), patch.object(user, 'download_cover', side_effect=fetch), patch.object(user, 'need_captcha', AsyncMock(return_value=False)):
            await user.cb_cover(callback, bot)
        callback.answer.assert_awaited_once()
        bot.send_photo.assert_not_awaited()
        bot.send_document.assert_awaited_once()
        self.assertEqual(delivered['data'], b'original-webp-image')
        self.assertEqual(delivered['filename'], 'cover.webp')
        self.assertEqual(delivered['chat_id'], 123)
        self.assertEqual(list(self.path.glob('cover_*')), [])
        self.assertFalse(user._active_cover_users)

    async def test_document_can_be_larger_than_photo_limit(self):
        await db.save_video_cover('token', 123, 'https://instagram.com/p/x', 'instagram')
        bot = SimpleNamespace(send_photo=AsyncMock(), send_document=AsyncMock(return_value=SimpleNamespace(message_id=9)), send_message=AsyncMock())
        async def fetch(url, platform, workdir):
            p = workdir / 'cover.png'
            with p.open('wb') as f:
                f.truncate(11 * 1024 * 1024)
            return p
        with patch('bot.config.TMP_DIR', self.path), patch('bot.config.USE_LOCAL_API', False), patch.object(user, 'download_cover', side_effect=fetch), patch.object(user, 'need_captcha', AsyncMock(return_value=False)):
            await user.cb_cover(self.callback(), bot)
        bot.send_document.assert_awaited_once()
        bot.send_photo.assert_not_awaited()

    async def test_document_larger_than_upload_limit_is_rejected(self):
        await db.save_video_cover('token', 123, 'https://instagram.com/p/x', 'instagram')
        bot = SimpleNamespace(send_document=AsyncMock(), send_message=AsyncMock())
        async def fetch(url, platform, workdir):
            p = workdir / 'cover.jpg'
            with p.open('wb') as f:
                f.truncate(50 * 1024 * 1024 + 1)
            return p
        with patch('bot.config.TMP_DIR', self.path), patch('bot.config.USE_LOCAL_API', False), patch.object(user, 'download_cover', side_effect=fetch), patch.object(user, 'need_captcha', AsyncMock(return_value=False)):
            await user.cb_cover(self.callback(), bot)
        bot.send_document.assert_not_awaited()
        bot.send_message.assert_awaited_once()
        self.assertEqual(list(self.path.glob('cover_*')), [])

    async def test_missing_and_wrong_chat_do_not_fetch(self):
        await db.save_video_cover('token', 123, 'https://youtube.com/watch?v=x', 'youtube')
        callback = self.callback(chat_id=999)
        with patch.object(user, 'download_cover', AsyncMock()) as fetch:
            await user.cb_cover(callback, SimpleNamespace())
        fetch.assert_not_awaited()
        self.assertTrue(callback.answer.await_args.kwargs['show_alert'])

    async def test_video_delivery_attaches_cover_button_even_as_document(self):
        video = self.path / 'video.mp4'
        video.write_bytes(b'video data')
        result = {'meta': {'title': 'Example'}, 'video_path': video, 'audio_path': None}
        trigger = SimpleNamespace(chat=SimpleNamespace(id=123), from_user=SimpleNamespace(id=7, username='user'))
        status = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
        bot = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(username='mybot')),
            send_video=AsyncMock(side_effect=TelegramBadRequest(method=SendPhoto(chat_id=123, photo='x'), message='bad video')),
            send_document=AsyncMock(return_value=SimpleNamespace(message_id=9)),
        )
        async def setting(key, default=''):
            return {'show_audio_separately': '0', 'auto_delete_hours': '0'}.get(key, default)
        with patch.object(user, 'download_media', AsyncMock(return_value=result)), \
             patch.object(user, 'get_setting', side_effect=setting), \
             patch.object(user, 'log_download', AsyncMock()):
            await user.do_download(trigger, bot, 'https://youtube.com/watch?v=x', 'youtube', status_msg=status)
        bot.send_document.assert_awaited_once()
        keyboard = bot.send_document.await_args.kwargs['reply_markup']
        data = [button.callback_data for row in keyboard.inline_keyboard for button in row]
        cover_data = next(item for item in data if item and item.startswith('cover:'))
        self.assertEqual(await db.get_video_cover(cover_data.partition(':')[2]),
                         (123, 'https://youtube.com/watch?v=x', 'youtube'))

    async def test_callback_failure_cleans_up_and_notifies(self):
        await db.save_video_cover('token', 123, 'https://youtube.com/watch?v=x', 'youtube')
        bot = SimpleNamespace(send_message=AsyncMock())
        with patch('bot.config.TMP_DIR', self.path), patch.object(user, 'download_cover', AsyncMock(side_effect=RuntimeError('failed'))), patch.object(user, 'need_captcha', AsyncMock(return_value=False)):
            await user.cb_cover(self.callback(), bot)
        bot.send_message.assert_awaited_once()
        self.assertEqual(list(self.path.glob('cover_*')), [])
        self.assertFalse(user._active_cover_users)

    async def test_callback_reports_no_cover(self):
        await db.save_video_cover('token', 123, 'https://youtube.com/watch?v=x', 'youtube')
        bot = SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock())
        with patch('bot.config.TMP_DIR', self.path), patch.object(user, 'download_cover', AsyncMock(return_value=None)), patch.object(user, 'need_captcha', AsyncMock(return_value=False)):
            await user.cb_cover(self.callback(), bot)
        bot.send_message.assert_awaited_once()
        bot.send_photo.assert_not_awaited()
        self.assertEqual(list(self.path.glob('cover_*')), [])


if __name__ == '__main__':
    unittest.main()
