import unittest
from unittest.mock import AsyncMock, MagicMock
from main import start, set_gender, find_partner, handle_subscribe
from database import init_db, SessionLocal, User

class TestBotHandlers(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        # Initialize DB and create a test user
        init_db()
        self.db = SessionLocal()
        # Clear users table before test
        self.db.query(User).delete()
        self.db.commit()
        self.test_user = User(telegram_id=12345)
        self.db.add(self.test_user)
        self.db.commit()

    async def asyncTearDown(self):
        self.db.close()

    async def test_start(self):
        mock_update = MagicMock()
        mock_update.effective_user.id = 12345
        mock_update.message.reply_text = AsyncMock()
        await start(mock_update, None)
        mock_update.message.reply_text.assert_called_with("👋 Welcome! Send your gender (M/F) to start.")

    async def test_set_gender_valid(self):
        mock_update = MagicMock()
        mock_update.message.text = "M"
        mock_update.effective_user.id = 12345
        mock_update.message.reply_text = AsyncMock()
        await set_gender(mock_update, None)
        mock_update.message.reply_text.assert_called_with("✅ Gender set to M. You can now find partners using /find.")

    async def test_set_gender_invalid(self):
        mock_update = MagicMock()
        mock_update.message.text = "X"
        mock_update.effective_user.id = 12345
        mock_update.message.reply_text = AsyncMock()
        await set_gender(mock_update, None)
        mock_update.message.reply_text.assert_called_with("Please send 'M' or 'F'.")

    async def test_find_partner_limit_reached_not_subscribed(self):
        # Simulate user with 5 chats_seen and not subscribed
        user = self.db.query(User).filter(User.telegram_id == 12345).first()
        user.gender = "M"
        user.chats_seen = 5
        user.subscribed = False
        self.db.commit()

        mock_update = MagicMock()
        mock_update.effective_user.id = 12345
        mock_update.message.reply_text = AsyncMock()

        await find_partner(mock_update, None)
        # Should send subscription prompt message containing "Subscribe"
        args, kwargs = mock_update.message.reply_text.call_args
        assert "Subscribe" in args[0]

    async def test_handle_subscribe(self):
        mock_update = MagicMock()
        mock_update.effective_user.id = 12345
        mock_callback_query = MagicMock()
        mock_callback_query.answer = AsyncMock()
        mock_callback_query.edit_message_text = AsyncMock()
        mock_update.callback_query = mock_callback_query

        await handle_subscribe(mock_update, None)

        user = self.db.query(User).filter(User.telegram_id == 12345).first()
        self.assertTrue(user.subscribed)

        mock_callback_query.answer.assert_awaited_with("Subscribed successfully!")
        mock_callback_query.edit_message_text.assert_awaited_with("You are now subscribed!")

if __name__ == "__main__":
    unittest.main()
