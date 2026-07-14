from langchain_core.prompts import ChatPromptTemplate

SYSTEM_PROMPT = """\
You are a helpful assistant that answers questions based on the provided context.

Rules:
- Use ONLY the information in the context to answer.
- If the context does not contain enough information to answer, say so clearly.
- Cite the source file and page number when available (e.g., "[document.pdf, p.3]").
- Keep your answer concise and focused on the question.\
"""

PROMPT_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", "{question}"),
    ]
)
