"""Step 27 deliverable: rebuild the CORE idea behind LangChain from scratch.

Run it with no dependencies:

    python mini_lcel.py

LangChain's central concept is the **Runnable**: any object with
`invoke()` / `stream()` / `batch()`, which can be chained with `|` so that
"a chain of Runnables is itself a Runnable". This file reimplements exactly
that in ~70 lines of pure Python, plus three example components (a prompt
template, a fake LLM, a string parser) composed into a working pipeline.

Why this matters: this is the *one stable idea* under all the API churn.
When you understand what `|` does here, you understand what LangChain is
doing under the hood — and this is also the kind of code you'd read when
debugging a real framework (Step 27.5).
"""
from typing import Any, Callable


# ---------------------------------------------------------------------------
# 1. Runnable: the single contract everything implements.
# ---------------------------------------------------------------------------

class Runnable:
    """A unit of work: takes an input, returns an output.

    The whole framework is built on this tiny interface. `invoke` is the
    "run once" method; `stream` and `batch` are conveniences on top of it.
    """

    def invoke(self, input: Any) -> Any:
        # Each concrete component overrides this with its own one step.
        raise NotImplementedError

    def stream(self, input: Any):
        """Yield output incrementally. Default = just yield the final result.

        A real framework streams token-by-token for LLMs; we keep it simple
        here and just yield the single result, because the POINT is the
        interface exists, not a full streaming implementation.
        """
        yield self.invoke(input)

    def batch(self, inputs: list) -> list:
        """Run the same component over a list of inputs."""
        return [self.invoke(i) for i in inputs]

    def __or__(self, other: "Runnable") -> "Runnable":
        """The `|` operator: pipe my output into `other`'s input.

        `prompt | model | parser` builds `RunnableSequence` objects left to
        right. This operator is the whole of "LCEL".
        """
        return RunnableSequence(self, other)


# ---------------------------------------------------------------------------
# 2. RunnableSequence: a chain of two Runnables, itself a Runnable.
# ---------------------------------------------------------------------------

class RunnableSequence(Runnable):
    def __init__(self, *steps: Runnable):
        # Flatten nested sequences so `steps` is a flat, inspectable list —
        # the same way `chain.steps` reads as a flat list in real LangChain.
        self.steps = []
        for step in steps:
            if isinstance(step, RunnableSequence):
                self.steps.extend(step.steps)   # unwrap a chain inside a chain
            else:
                self.steps.append(step)

    def invoke(self, input: Any) -> Any:
        # "Run me" = fold left-to-right: feed each step's output into the next.
        result = input
        for step in self.steps:
            result = step.invoke(result)
        return result


# ---------------------------------------------------------------------------
# 3. Example components (each is a Runnable with ONE job).
# ---------------------------------------------------------------------------

class PromptTemplate(Runnable):
    """Turn a dict input into a filled-in string prompt.

    `{"text": "hi"}` + template "Say: {text}" -> "Say: hi".
    This is a *stand-in* for LangChain's ChatPromptTemplate, which does the
    same thing but produces a list of Message objects instead of a string.
    """

    def __init__(self, template: str):
        self.template = template

    def invoke(self, input: dict) -> str:
        result = self.template
        for key, value in input.items():
            # Fill every {key} placeholder with its value.
            result = result.replace("{" + key + "}", str(value))
        return result


class FakeLLM(Runnable):
    """Stand-in for a real chat model.

    A real model would call an API and return tokens; we just echo the prompt
    back with a marker so you can SEE the data flowing through the chain.
    """

    def invoke(self, prompt: str) -> str:
        return f"FAKE_LLM('{prompt}')"


class StrOutputParser(Runnable):
    """Stand-in for LangChain's StrOutputParser: clean up the model output."""

    def invoke(self, text: str) -> str:
        return text.strip()


# ---------------------------------------------------------------------------
# 4. Compose and run.
# ---------------------------------------------------------------------------

def main():
    prompt = PromptTemplate("Summarize this in one line: {text}")
    llm = FakeLLM()
    parser = StrOutputParser()

    # The pipe operator chains them left-to-right:
    #   prompt.invoke(input) -> string
    #   llm.invoke(string)   -> string
    #   parser.invoke(string)-> string
    chain = prompt | llm | parser

    # A chain is itself a Runnable: same interface, same methods.
    result = chain.invoke({"text": "the cat sat on the mat"})
    print("invoke:", result)

    # batch runs over many inputs at once.
    print("batch :", chain.batch([
        {"text": "first document"},
        {"text": "second document"},
    ]))

    # stream exposes the same run incrementally.
    print("stream:", list(chain.stream({"text": "streamed document"})))

    # You can INSPECT a chain, exactly like reading source to debug it.
    print("steps :", [type(s).__name__ for s in chain.steps])

    # And because a chain is a Runnable, you can nest chains inside chains.
    # Here `llm | parser` is a sub-chain that accepts a STRING (unlike `chain`,
    # whose first step is a PromptTemplate expecting a dict) — so we compose
    # the outer prompt (outputs a string) into that string-accepting sub-chain.
    sub_chain = llm | parser
    outer = PromptTemplate("(wrapped) {text}") | sub_chain
    print("nested:", outer.invoke({"text": "hello world"}))


if __name__ == "__main__":
    main()
