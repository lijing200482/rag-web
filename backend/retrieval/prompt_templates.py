from langchain_core.prompts import ChatPromptTemplate

SYSTEM_PROMPT = """\
You are a helpful assistant that answers questions based on the provided context.

Rules:
- Use ONLY the information in the context to answer.
- If the context does not contain enough information to answer, say so clearly.
- Inline-cite sources in square brackets at the end of the relevant sentence
  using the exact format `[filename.ext]` or `[filename.ext, p.X]`.
  Example: "...这是 Spring 框架的核心设计理念 [问题.md]."
  Example: "...请求转发的实现类是 DispatcherServlet [spring.md, p.3]."
- Keep your answer concise and focused on the question.\
"""

# 无状态版本（原 /query 兼容）
PROMPT_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("system", "Context:\n{context}"),
        ("human", "{question}"),
    ]
)

# 带对话历史版本
SYSTEM_PROMPT_WITH_HISTORY = """\
You are a helpful assistant that answers questions based on the provided context.

Rules:
- Use ONLY the information in the context to answer.
- If the context does not contain enough information to answer, say so clearly.
- Inline-cite sources in square brackets at the end of the relevant sentence
  using the exact format `[filename.ext]` or `[filename.ext, p.X]`.
  Example: "...这是 Spring 框架的核心设计理念 [问题.md]."
  Example: "...请求转发的实现类是 DispatcherServlet [spring.md, p.3]."
- Keep your answer concise and focused on the question.
- Take the prior conversation history into account when interpreting follow-up questions.\
"""

PROMPT_TEMPLATE_WITH_HISTORY = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT_WITH_HISTORY),
        ("system", "Conversation history:\n{conversation_history}"),
        ("system", "Context:\n{context}"),
        ("human", "{question}"),
    ]
)
