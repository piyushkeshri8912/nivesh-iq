import os
import logging
from app.core.config import settings
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

logger = logging.getLogger(__name__)

# Configure environment variables for langchain-google-genai to route to Vertex AI
try:
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
    os.environ["GOOGLE_CLOUD_PROJECT"] = settings.VERTEX_PROJECT_ID
    os.environ["GOOGLE_CLOUD_LOCATION"] = settings.VERTEX_LOCATION 
    
    # Initialize globally accessible model singletons
    
    # 1. Flash Lite Model: For low-level classifications and fast tasks
    flash_lite_model = ChatGoogleGenerativeAI(
        model=getattr(settings, "VERTEX_FLASH_LITE_MODEL", "gemini-2.5-flash-lite"),
        temperature=0.2,
        max_tokens=8192
    )
    
    # 2. Flash Model: For tool planning and function calling
    flash_model = ChatGoogleGenerativeAI(
        model=getattr(settings, "VERTEX_FLASH_MODEL", "gemini-2.5-flash"),
        temperature=0.2,
        max_tokens=10000
    )
    
    # 3. Pro Model: For deep financial strategist analysis and report writing
    pro_model = ChatGoogleGenerativeAI(
        model=getattr(settings, "VERTEX_PRO_MODEL", "gemini-2.5-pro"),
        temperature=0.1,
        max_tokens=10000
    )
    
    logger.info("Successfully initialized global LangChain model singletons.")
except Exception as e:
    logger.error(f"Global model initialization failed: {e}", exc_info=True)
    raise RuntimeError(f"Global model initialization failed: {e}") from e
