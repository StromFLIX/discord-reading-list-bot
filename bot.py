from pydantic_settings import BaseSettings, SettingsConfigDict
import os
import asyncio
from dotenv import load_dotenv
import discord
from discord.ext import commands
from src.reader import Reader
from src.summarizer import Summarizer
from src.github_client import GitHubClient
import re
import datetime

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='DISCORD_', env_file='.env')

    bot_token: str  # will be read from `DISCORD_BOT_TOKEN`
    openrouter_api_key: str = "sk-..." # Default or from env
    openrouter_model: str = "openai/gpt-4o-mini"
    
    github_token: str = "" # DISCORD_GITHUB_TOKEN
    github_repo: str = ""  # DISCORD_GITHUB_REPO (e.g. "username/repo")
    github_path_prefix: str = ""  # DISCORD_GITHUB_PATH_PREFIX (e.g. "articles" or "knowledge-base")

settings = Settings()

# Intents: needed so the bot can see message content
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
reader = Reader()
summarizer = Summarizer(api_key=settings.openrouter_api_key, model=settings.openrouter_model)
github_client = GitHubClient(token=settings.github_token, repo_name=settings.github_repo, path_prefix=settings.github_path_prefix) if settings.github_token else None

class ReadStatusView(discord.ui.View):
    def __init__(self, summary_data, original_content, content_type, source_name):
        super().__init__(timeout=30)
        self.summary_data = summary_data
        self.original_content = original_content # Text content or bytes
        self.content_type = content_type # "link" or "pdf"
        self.source_name = source_name # URL or Filename
        self.message: discord.Message = None

    async def on_timeout(self):
        if hasattr(self, 'message') and self.message:
            # Disable buttons
            for child in self.children:
                child.disabled = True
            await self.message.edit(view=self)
            
            # Perform "New to me" logic (is_read=False)
            await self.process_upload(interaction=None, is_read=False)

    async def process_upload(self, interaction: discord.Interaction | None, is_read: bool):
        if not github_client:
            if interaction:
                await interaction.response.send_message("GitHub client not configured.", ephemeral=True)
            return

        if interaction:
            await interaction.response.defer()
            # Disable buttons to prevent double-click
            for child in self.children:
                child.disabled = True
            await interaction.message.edit(view=self)
        
        # Generate slug
        slug = "".join([c if c.isalnum() else "-" for c in self.summary_data.title.lower()]).strip("-")
        slug = re.sub(r'-+', '-', slug) # Remove duplicate dashes
        
        # 1. Upload Summary Markdown
        caveats_section = ""
        if self.summary_data.caveats:
            caveats_section = "\n" + "\n".join([f"> {c}" for c in self.summary_data.caveats]) + "\n"

        # Determine source link
        source_link = self.source_name
        if self.content_type == "pdf":
            # Relative link to the PDF in the same folder structure
            source_link = f"{slug}/{self.source_name}"

        # Generate tags
        def to_snake(s: str) -> str:
            return s.lower().strip().replace(' ', '_')

        tags_list = []
        if self.summary_data.topics:
            tags_list.append(", ".join([f"#topic/{to_snake(t)}" for t in self.summary_data.topics]))
        if self.summary_data.issues:
            tags_list.append(", ".join([f"#issue/{to_snake(i)}" for i in self.summary_data.issues]))
        if self.summary_data.sentiment:
            tags_list.append(f"#sentiment/{to_snake(self.summary_data.sentiment)}")
        if self.summary_data.people:
            tags_list.append(", ".join([f"#people/{to_snake(p)}" for p in self.summary_data.people]))
            
        tags_section = "\n".join(tags_list)

        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        md_content = f"""# {self.summary_data.title}

> Source: {source_link}
> Added: {date_str}

{tags_section}

{self.summary_data.summary}
{caveats_section}
---
"""
        md_path = f"articles/{slug}.md"
        github_client.upload_file(md_path, f"Add summary for {self.summary_data.title}", md_content)
        
        # Construct GitHub URL
        full_path = f"{settings.github_path_prefix}/{md_path}" if settings.github_path_prefix else md_path
        repo_url = f"https://github.com/{settings.github_repo}/blob/main/{full_path}"
        msg = f"Summary uploaded: <{repo_url}>"

        # 2. Upload PDF if applicable
        if self.content_type == "pdf":
            pdf_path = f"articles/{slug}/{self.source_name}"
            github_client.upload_file(pdf_path, f"Add PDF for {self.summary_data.title}", self.original_content)
            # msg += f"\nPDF uploaded."

        # 3. Update reading-list.md
        reading_list_path = "reading-list.md"
        current_list = github_client.get_file_content(reading_list_path) or "# Reading List\n\n"
        
        check_mark = "x" if is_read else " "
        relative_path = f"articles/{slug}.md"
        new_entry = f"- [{check_mark}] {date_str} - [{self.summary_data.title}]({relative_path})"
        
        # Parse existing list to sort
        lines = current_list.splitlines()
        header = []
        entries = []
        
        for line in lines:
            if line.strip().startswith("- ["):
                entries.append(line)
            else:
                header.append(line)
        
        # Add new entry if not present
        if not any(f"[{self.summary_data.title}]" in e for e in entries):
            entries.insert(0, new_entry) # Add to top (newest first)
            msg += f"\nReading list updated."
        else:
            msg += f"\nAlready in reading list."
            
        # Reconstruct file content
        updated_list = "\n".join(header).strip() + "\n\n" + "\n".join(entries) + "\n"
        github_client.upload_file(reading_list_path, f"Update reading list for {self.summary_data.title}", updated_list)

        if interaction:
            await interaction.followup.send(msg)
        elif hasattr(self, 'message') and self.message:
            await self.message.reply(msg + "\n*(Automatically uploaded due to timeout)*")
        
        self.stop()

    @discord.ui.button(label="Already Read", style=discord.ButtonStyle.secondary, emoji="✅")
    async def already_read(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_upload(interaction, is_read=True)

    @discord.ui.button(label="Not yet read", style=discord.ButtonStyle.primary, emoji="📤")
    async def not_yet_read(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_upload(interaction, is_read=False)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id={bot.user.id})")


def should_start_thread(message: discord.Message) -> bool:
    """
    Put your logic here:
    - specific channel ID
    - messages that start with some keyword
    - etc.
    """
    # Example: ignore bot messages
    if message.author.bot:
        return False

    # Example: only in a specific channel (replace with your channel ID)
    TARGET_CHANNEL_ID = 1441751233303154731  # <- your channel id here
    if message.channel.id != TARGET_CHANNEL_ID:
        return False

    return True


@bot.event
async def on_message(message: discord.Message):
    # First let commands still work
    await bot.process_commands(message)

    # Handle replies inside threads
    if isinstance(message.channel, discord.Thread):
        if message.author.bot: return # Ignore bot's own messages in threads
        print(f"Received follow-up in thread {message.channel.id}: {message.content}")
        # Add your logic here (e.g. save to DB, forward to admin channel)
        return

    if not should_start_thread(message):
        return

        # Process PDFs
    if message.attachments:
        for attachment in message.attachments:
            if attachment.filename.lower().endswith('.pdf'):
                print(f"Processing PDF: {attachment.filename}")
                
                # Create thread if needed
                thread = message.channel if isinstance(message.channel, discord.Thread) else None
                created_thread = False
                if not thread:
                    try:
                        thread = await message.create_thread(name=f"Analysis: {attachment.filename}", auto_archive_duration=60)
                        created_thread = True
                    except Exception as e:
                        print(f"Could not create thread: {e}")
                        thread = message.channel

                try:
                    file_bytes = await attachment.read()
                    # Run CPU-bound task in a separate thread
                    text = await asyncio.to_thread(reader.read_pdf, file_bytes)
                    print(f"--- PDF Content ({attachment.filename}) ---\n{text[:200]}...\n-----------------------------------")
                    
                    if not text or len(text.strip()) < 50:
                        raise ValueError("PDF content is empty or too short")
                    
                    summary = await summarizer.summarize(text)
                    
                    # Rename thread if we created it
                    if created_thread and isinstance(thread, discord.Thread):
                        await thread.edit(name=summary.title[:100])

                    view = ReadStatusView(
                        summary_data=summary,
                        original_content=file_bytes,
                        content_type="pdf",
                        source_name=attachment.filename
                    )
                    
                    view.message = await thread.send(
                        f"**PDF Analysis: {summary.title}**\n\n{summary.summary}\n\n*Caveats: {', '.join(summary.caveats) if summary.caveats else 'None'}*",
                        view=view
                    )

                except Exception as e:
                    print(f"Failed to process PDF: {e}")
                    await thread.send(f"Failed to process PDF {attachment.filename}: {e}")

    # Process Links
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    urls = re.findall(url_pattern, message.content)
    for url in urls:
        print(f"Processing Link: {url}")
        
        # Check for YouTube
        youtube_regex = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com\/watch\?v=|youtu\.be\/)([\w-]+)'
        yt_match = re.search(youtube_regex, url)
        
        processing_url = url
        if yt_match:
            video_id = yt_match.group(1)
            processing_url = f"https://youtubetotranscript.com/transcript?v={video_id}"
            print(f"Detected YouTube URL. Fetching transcript from: {processing_url}")
        
        # Create thread if needed
        thread = message.channel if isinstance(message.channel, discord.Thread) else None
        created_thread = False
        if not thread:
            try:
                thread = await message.create_thread(name=f"Analysis: Link", auto_archive_duration=60)
                created_thread = True
            except Exception as e:
                print(f"Could not create thread: {e}")
                thread = message.channel

        try:
            # Run async read_link
            text = reader.read_link(processing_url)
            print(f"--- Link Content ({processing_url}) ---\n{text[:200]}...\n-----------------------------------")
            
            if not text or len(text.strip()) < 50:
                raise ValueError("Link content is empty or too short")
            
            summary = await summarizer.summarize(text)
            
            # Rename thread if we created it
            if created_thread and isinstance(thread, discord.Thread):
                await thread.edit(name=summary.title[:100])

            view = ReadStatusView(
                summary_data=summary,
                original_content=text, # For links, we save the extracted text
                content_type="link",
                source_name=url # Keep original URL as source
            )
            
            view.message = await thread.send(
                f"**Link Analysis: {summary.title}**\n\n{summary.summary}\n\n*Caveats: {', '.join(summary.caveats) if summary.caveats else 'None'}*",
                view=view
            )

        except Exception as e:
            print(f"Failed to process Link: {e}")
            await thread.send(f"Failed to process Link {url}: {e}")


if __name__ == "__main__":
    bot.run(settings.bot_token)
