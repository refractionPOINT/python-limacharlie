# Telegram

Output detections and audit (only) to a Telegram chat, group, or channel.

- `bot_token`: the Telegram Bot API token obtained from @BotFather.
- `chat_id`: the target chat, group, or channel ID to send messages to.
- `parse_mode`: (optional) message formatting mode: `Markdown`, `MarkdownV2`, or `HTML`.
- `message`: (optional) a template string for custom message formatting.

Example:

```text
bot_token: 123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
chat_id: -1001234567890
parse_mode: Markdown
```

## Provisioning

To use this Output, you need to create a Telegram Bot:

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts to name your bot
3. Copy the bot token provided — this is the `bot_token` you need in LimaCharlie
4. Add the bot to the chat, group, or channel where you want to receive messages
5. For channels, add the bot as an administrator with "Post Messages" permission
6. Get the `chat_id` for your target:
    - For **private chats**: message the bot, then visit `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your chat ID
    - For **groups**: add the bot to the group, send a message, then check `getUpdates` for the group's chat ID (a negative number)
    - For **public channels**: use `@channelusername` as the chat ID
