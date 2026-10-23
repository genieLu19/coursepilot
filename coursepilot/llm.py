import hashlib

from openai import OpenAI


class OpenAIProvider:
    def __init__(self, config, store):
        self.model = config.model
        self.embedding_model = config.embedding_model
        self.store = store
        self.client = OpenAI(api_key=config.api_key or "not-configured", timeout=60, max_retries=1)
        self.configured = bool(config.api_key)
        self.usage = {"input_tokens": 0, "output_tokens": 0, "embedding_tokens": 0}

    def require_key(self):
        if not self.configured:
            raise ValueError("Добавь OPENAI_API_KEY в .env.local и перезапусти приложение.")

    def embed(self, texts):
        self.require_key()
        results = [None] * len(texts)
        missing = []
        for index, text in enumerate(texts):
            key = hashlib.sha256((self.embedding_model + "\n" + text).encode()).hexdigest()
            cached = self.store.cached_embedding(key)
            if cached is not None:
                results[index] = cached
            else:
                missing.append((index, key, text))
        for start in range(0, len(missing), 32):
            batch = missing[start:start + 32]
            response = self.client.embeddings.create(model=self.embedding_model, input=[r[2] for r in batch])
            self.usage["embedding_tokens"] += response.usage.total_tokens
            for item in response.data:
                index, key, _ = batch[item.index]
                results[index] = item.embedding
                self.store.cache_embedding(key, item.embedding)
        return results

    def respond(self, **kwargs):
        self.require_key()
        response = self.client.responses.create(model=self.model, store=False, max_output_tokens=2400, **kwargs)
        if response.usage:
            self.usage["input_tokens"] += response.usage.input_tokens
            self.usage["output_tokens"] += response.usage.output_tokens
        return response

    def structured(self, schema, instructions, data):
        self.require_key()
        response = self.client.responses.parse(
            model=self.model, store=False, max_output_tokens=3000,
            instructions=instructions, input=data, text_format=schema)
        if response.usage:
            self.usage["input_tokens"] += response.usage.input_tokens
            self.usage["output_tokens"] += response.usage.output_tokens
        if response.output_parsed is None:
            raise ValueError("Модель не вернула корректный структурированный результат. Попробуй ещё раз.")
        return response.output_parsed
