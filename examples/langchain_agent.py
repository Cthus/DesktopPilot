"""把 DesktopPilot 工具接进 LangChain agent。

运行前：
    pip install 'desktop-pilot[langchain]' langchain-openai
    export OPENAI_API_KEY=sk-...   # Windows: set OPENAI_API_KEY=sk-...

运行：
    python examples/langchain_agent.py

agent 会自己决定调用哪些桌面工具，完成"打开浏览器搜 Python 教程"这类任务。
"""
from __future__ import annotations

import os

from desktop_pilot import Desktop
from desktop_pilot.integrations.langchain import get_tools


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        print("请先设置 OPENAI_API_KEY 环境变量。")
        return

    # 延迟导入，让没装 langchain 的用户也能 import 本文件不报错。
    from langchain.agents import AgentExecutor, create_tool_calling_agent
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    with Desktop() as bot:
        tools = get_tools(bot)

        llm = ChatOpenAI(model="gpt-4o", temperature=0)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是一个能操作用户电脑桌面的助手。"
                    "优先使用结构化的控件工具（desktop_click_button、"
                    "desktop_type_into、desktop_wait_for），"
                    "实在拿不到控件时再用坐标点击或截图。",
                ),
                ("placeholder", "{chat_history}"),
                ("human", "{input}"),
                ("placeholder", "{agent_scratchpad}"),
            ]
        )

        agent = create_tool_calling_agent(llm, tools, prompt)
        executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

        executor.invoke(
            {"input": "打开浏览器，搜索 'Python 教程'，并打开第一个搜索结果。"}
        )


if __name__ == "__main__":
    main()
