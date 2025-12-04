
import inspect
from pydantic_ai.models.openai import OpenAIModel

try:
    print(inspect.signature(OpenAIModel.__init__))
except Exception as e:
    print(e)

try:
    # Also check if there is an underlying OpenAIChatModel if imported
    pass
except:
    pass

