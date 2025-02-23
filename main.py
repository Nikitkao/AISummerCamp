import asyncio
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile, ContentType
import pathlib
from openai import OpenAI
import uuid
import soundfile as sf

class Settings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str
    OPEN_AI_API_TOKEN: str

    model_config = SettingsConfigDict(env_file='settings.env', env_file_encoding='utf-8')

def convert_oga_to_mp3(input_file, output_file):
    data, samplerate = sf.read(input_file)
    sf.write(output_file, data, samplerate)

config = Settings()
TOKEN = config.TELEGRAM_BOT_TOKEN
OPEN_AI_API_TOKEN = config.OPEN_AI_API_TOKEN

client = OpenAI(api_key=OPEN_AI_API_TOKEN)

dp = Dispatcher()
bot: Bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(f"Hello, {html.bold(message.from_user.full_name)}!")

@dp.message()
async def echo_handler(message: Message) -> None:

    input_file = ''
    output_file = ''
    speech_file_path = ''

    if message.content_type != ContentType.VOICE:
        await message.answer("Доступны только голосовые сообщения")
        return
    
    try:
        file_id = message.voice.file_id
        file = await bot.get_file(file_id)
        file_path = file.file_path

        callbackGuid = str(uuid.uuid4())

        await bot.download_file(file_path, f"voice{callbackGuid}.oga")
        
        input_file = f"{pathlib.Path(__file__).parent.resolve()}/voice{callbackGuid}.oga"
        output_file = f"{pathlib.Path(__file__).parent.resolve()}/voice{callbackGuid}.wav"

        convert_oga_to_mp3(input_file, output_file)

        audio_file = open(output_file, "rb")

        transcription = client.audio.transcriptions.create(model="whisper-1", file=audio_file)

        assistant = client.beta.assistants.create(
            name="Nikita Rakitin",
            instructions="You are a personal assistant. Helping people to solve problems.",
            tools=[{"type": "code_interpreter"}],
            model="gpt-4o")
        
        thread = client.beta.threads.create()

        client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=transcription.text
            )

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant.id,
            instructions=f"Please address the user as {message.from_user.full_name}. The user uses Telegram"
            )
        
        if run.status == 'completed': 
            messages = client.beta.threads.messages.list(
            thread_id=thread.id
            )

            speech_file_path = pathlib.Path(__file__).parent / f"speech{callbackGuid}.mp3"
            response1 = client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=messages.data[0].content[0].text.value
                )

            response1.stream_to_file(speech_file_path)
            speech_file_path = speech_file_path.absolute().as_posix()

            await bot.send_voice(chat_id=message.chat.id, voice=FSInputFile(speech_file_path))
        else:
            await message.answer(run.status)
    except Exception as e:
        print(e)
        await message.answer("Что-то пошло не так, попробуйте еще раз")

    pathlib.Path.unlink(speech_file_path, True)
    pathlib.Path.unlink(input_file, True)
    pathlib.Path.unlink(output_file, True)

async def main() -> None:
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

