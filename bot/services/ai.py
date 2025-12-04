import os
import json
import logging
import random
from typing import Optional, List, Dict, Any
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class AIClient:
    def __init__(self, config):
        self.config = config
        
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        api_key = openrouter_key or config.api_key
        base_url = None
        self.model_name = config.model

        if openrouter_key:
            base_url = "https://openrouter.ai/api/v1"
            if "/" not in self.model_name:
                self.model_name = f"openai/{self.model_name}"
        
        if base_url:
            self.client = AsyncOpenAI(
                base_url=base_url,
                api_key=api_key,
            )
        else:
            self.client = AsyncOpenAI(
                api_key=api_key
            )

    async def generate_initial_greeting(self) -> str:
        try:
            tasks = [
                "рассказать анекдот",
                "загадать игроку загадку",
                "сделать комплимент банкиру",
                "произнести тост",
                "придумать оправдание проигрышу"
            ]
            topics = [
                "анонимные имиджборды",
                "рэп-батл",
                "2ch",
                "зумеры",
                "казино",
                "коллекторы",
                "ставки",
                "киберспорт",
                "криптовалюты",
                "Илья Мэддисон",
                "русские ютуберы",
                "русский рэп",
                "игра STALKER",
                "крафтовое пиво",
                "кино"
            ]

            selected_task = random.choice(tasks)
            
            if random.random() < 0.7:
                topic_part = f"Используй тему: {random.choice(topics)}."
            else:
                topic_part = "Придумай случайную тему, актуальную для молодого человека в России."

            prompt = (
                "Ты — циничный и хитрый банкир в казино. Твой характер: смесь Джокера и уставшего коллектора. "
                "Ты не хочешь давать кредит, поэтому даешь задание.\n\n"
                
                f"ЗАДАНИЕ: {selected_task}\n"
                f"КОНТЕКСТ: {topic_part}\n\n"
                
                "ИНСТРУКЦИЯ:\n"
                "1. Сформулируй требование к игроку одной фразой.\n"
                "2. ОБЯЗАТЕЛЬНО объедини ЗАДАНИЕ и КОНТЕКСТ. Тема должна влиять на то, О ЧЕМ задание, или В КАКОМ СТИЛЕ оно должно быть выполнено.\n"
                "3. Не пиши 'Задание: ...', не здоровайся. Сразу требуй.\n\n"
                
                "ПРИМЕРЫ ХОРОШИХ ОТВЕТОВ:\n"
                "- (Задание: анекдот, Тема: русский рэп) -> 'Расскажи мне анекдот про Тимати или Басту. И чтобы было смешно, йоу.'\n"
                "- (Задание: комплимент, Тема: Илья Мэддисон) -> 'Похвали меня так, как будто ты Илья Мэддисон обозреваешь шедевр 10 из 10.'\n"
                "- (Задание: оправдание, Тема: STALKER) -> 'Объясни мне, куда делись деньги. Говори так, будто оправдываешься перед Сидоровичем за потерянный хабар.'\n"
                "- (Задание: загадка, Тема: коллекторы) -> 'Отгадай загадку: в дверь стучат, но не гости, кто это?.'\n\n"
                
                "Твой ответ (только текст требования):"
            )
            
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "system", "content": prompt}],
                temperature=0.6
            )
            content = response.choices[0].message.content.strip()
            # Fallback if empty
            if not content:
                return f"Ну что, {selected_task}. Живо!"
            return content

        except Exception as e:
            logger.error(f"Error generating greeting: {e}")
            return "Эй, ты! Хочешь денег? Удиви меня!"

    async def generate_response(self, history: List[dict]) -> dict:
        """
        Processes the user's answer and returns a reward based on strict evaluation.
        """
        try:
            # Extract user's last message
            user_message = "..."
            bot_task = "Неизвестное задание"
            
            # Iterate backwards to find user message and the preceding assistant message
            found_user = False
            for i in range(len(history) - 1, -1, -1):
                msg = history[i]
                if msg['role'] == 'user' and not found_user:
                    user_message = msg['content']
                    found_user = True
                    # Look for the assistant message before this user message
                    if i > 0 and history[i-1]['role'] == 'assistant':
                        bot_task = history[i-1]['content']
                    break
            
            # Prompt to evaluate (accept) the answer
            system_prompt = (
                "Ты — веселый Джокер в казино, оценивающий выполнение задания кредитора. "
                f"ЗАДАНИЕ БЫЛО: \"{bot_task}\". "
                f"ОТВЕТ ИГРОКА: \"{user_message}\". \n\n"
                
                "ТВОЯ ЗАДАЧА: Оцени ответ в 3 шага:\n"
                "1. ПРОВЕРЬ КОНТЕКСТ: Понимает ли игрок тему? Учитывай культурные отсылки (фильмы, музыка, мемы России/СНГ).\n"
                "2. ОЦЕНИ КРЕАТИВ: Есть ли юмор, находчивость или старания? Распознавай мета-шутки и второй слой и оценивай их выше.\n"
                "3. ПРОВЕРЬ НА AI: Признаки AI-генерации (идеальная грамматика, формальные кавычки/тире, академический стиль без сленга).\n\n"
                
                "ШКАЛА ОЦЕНКИ:\n"
                "МУСОР (1-19): Полный игнор темы, требование денег, явная лень или копипаст.\n"
                "СКУКА (20-39): Формальный ответ без креатива, AI-генерация, 'для галочки'.\n"
                "КРЕАТИВ (40-69): Соблюдена тема/стиль, есть юмор или находчивость.\n"
                "ЗОЛОТО (70-100): Гениальная шутка, неожиданная отсылка, вызывает смех.\n\n"
                
                "ПРАВИЛА:\n"
                "Сравнивай с baseline: ответ лучше, чем 'просто дай деньги'? Лучше, чем сухой пересказ задания? Если да - минимум 50.\n"
                "- Не штрафуй за грамматические ошибки в творческих ответах, сленг, короткие ответы (при соответствии теме).\n"
                "- Штрафуй за AI-шаблоны, игнор темы, отсутствие попыток.\n\n"
                
                "ПРИМЕРЫ:\n"
                "- 'Расскажи тост про Тарантино' - 'мистер розовый, давайте выпьем за футфетиш' → 95 (отсылка к Тарантино, креативно)\n"
                "- Загадка — точное одно слово по сути → 80–100\n"
                "- Идеально оформленный текст без души → 25 (AI-генерация)\n"
                "- Короткий, но меткий ответ по теме → 60+ (ценить старания и находчивость)\n\n"
                
                "КОММЕНТАРИИ: Краткие, соответствуют оценке - от критики до уважения.\n\n"
                
                "Формат ответа строго JSON: { \"reasoning\": \"Мысли о том, как оценить ответ\", \"text\": \"Ответ пользователю\", \"reward\": число }"
            )

            messages = [
                {"role": "system", "content": system_prompt}
            ]

            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.4
            )

            content = response.choices[0].message.content
            
            # Try to parse JSON
            try:
                # Simple cleanup to handle code blocks
                clean_content = content
                if "```" in clean_content:
                     match = clean_content.split("```")
                     # Check if there is json block
                     for block in match:
                         if block.strip().startswith("json"):
                             clean_content = block.strip()[4:]
                             break
                         elif block.strip().startswith("{"):
                             clean_content = block.strip()
                             break
                
                # Fallback cleanup for non-codeblock json
                start = clean_content.find('{')
                end = clean_content.rfind('}')
                if start != -1 and end != -1:
                    clean_content = clean_content[start:end+1]

                data = json.loads(clean_content)
                text = data.get("text", "Ладно, вот твои копейки.")
                reward = int(data.get("reward", 15))
            except Exception:
                logger.warning(f"Failed to parse JSON from AI: {content}")
                text = "Ты меня утомил. Бери мелочь и уходи."
                reward = 15

            # Ensure reward is within bounds
            try:
                reward = max(1, min(100, int(reward)))
            except:
                reward = 15

            return {
                "content": text,
                "completion_data": {
                    "done": True,
                    "score": 10,
                    "reward": reward,
                    "comment": text
                }
            }

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return {
                "content": "Банк закрыт на переучет. Проваливай.",
                "completion_data": {
                    "done": True,
                    "score": 0,
                    "reward": 1,
                    "comment": "Ошибка API"
                }
            }
