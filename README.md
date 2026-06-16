# 💬 Emoji Studio

Have you ever thought '*there really should be an emoji for this*'? I have. Constantly.

But here's what makes this more interesting: **LLMs use emojis**. They use them naturally in responses, and they're genuinely expressive when they do, allowing LLMs to express themselves better visually. The catch is that they're locked into whatever emoji vocabulary existed in their training data. They can't use something they've never seen. Furthermore, some emojis are more popular than others, which affects how likely the model is to reach for them.
 
So I started wondering: what if you could just... invent new ones and teach an LLM to use them when you talk to it?

**Emoji Studio** is a chat experience that explores new ways for humans and AI to communicate. Rather than relying on existing emojis and language, you and the assistant create entirely new emojis together, define their meanings, and build a shared visual vocabulary that evolves throughout your conversations.

## 🔗 Links

🚀 [Try it](https://huggingface.co/spaces/build-small-hackathon/emoji_studio) |
📓 [Read blog post](https://huggingface.co/blog/build-small-hackathon/emoji-studio) |
🎬 [Watch demo video](https://huggingface.co/spaces/build-small-hackathon/emoji_studio/resolve/main/demo.mp4) |
💬 [Social post](https://www.reddit.com/r/huggingface/comments/1u4x5fr/emoji_studio_my_project_for_hf_build_small/)

## 🎬 Demo

<video controls preload="metadata" width="100%">
  <source src="./demo.mp4" type="video/mp4">
</video>

## 🛠️ Models

- **Qwen/Qwen3-8B** — chat and tool-calling to decide when to generate a new emoji
- **FLUX.1-schnell** — image generation for the emoji itself
- **Rembg** — background removal for a clean transparent finish

A total of $8B+12B=20B$ parameters. The first two models run via the Hugging Face Inference API.

## 📋 Submission details

- **Track:** Thousand Token Wood 🍄
- **Bonus quests:** 🎨 Off-Brand · 📓 Field Notes
- Built with Gradio 🐾 and hosted on Hugging Face 🤗


