import io
from pypdf import PdfReader
import trafilatura

class Reader:
    def read_pdf(self, file_bytes: bytes) -> str:
        """Reads a PDF from bytes and returns the text. Raises exception on failure."""
        reader = PdfReader(io.BytesIO(file_bytes))
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()

    def read_link(self, url: str) -> str:
        """Fetches a URL and extracts the text from the article. Raises exception on failure."""
        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            raise ValueError("Could not fetch content (empty response)")
        
        text = trafilatura.extract(downloaded)
        if text is None:
            raise ValueError("Could not extract text from content")
            
        return text
