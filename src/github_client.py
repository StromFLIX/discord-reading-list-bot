from github import Github, Auth
from github.Repository import Repository
import base64
from typing import Optional

class GitHubClient:
    def __init__(self, token: str, repo_name: str, path_prefix: str = ""):
        self.github = Github(auth=Auth.Token(token))
        self.repo_name = repo_name
        self.path_prefix = path_prefix.rstrip("/") if path_prefix else ""
        self._repo: Optional[Repository] = None

    @property
    def repo(self) -> Repository:
        if not self._repo:
            self._repo = self.github.get_repo(self.repo_name)
        return self._repo

    def get_file_content(self, path: str, branch: str = "main") -> Optional[str]:
        """Retrieves the content of a file as a string. Returns None if not found."""
        if self.path_prefix:
            path = f"{self.path_prefix}/{path.lstrip('/')}"
        
        try:
            contents = self.repo.get_contents(path, ref=branch)
            return contents.decoded_content.decode("utf-8")
        except Exception:
            return None

    def upload_file(self, path: str, message: str, content: str | bytes, branch: str = "main") -> str:
        """
        Uploads a file to the repository.
        If content is str, it's treated as text (e.g. Markdown).
        If content is bytes, it's treated as binary (e.g. PDF).
        """
        if self.path_prefix:
            path = f"{self.path_prefix}/{path.lstrip('/')}"

        try:
            # Check if file exists to update or create
            try:
                contents = self.repo.get_contents(path, ref=branch)
                # Update existing file
                self.repo.update_file(contents.path, message, content, contents.sha, branch=branch)
                return f"Updated {path}"
            except Exception:
                # Create new file
                self.repo.create_file(path, message, content, branch=branch)
                return f"Created {path}"
        except Exception as e:
            return f"Error uploading to GitHub: {e}"
