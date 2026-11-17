from vllm import LLM, SamplingParams

MODEL = "/sadata/nikkothari/kai-scheduler-lab/.cache/gemma-4-E2B-it"
PROMPTS = [
    "Explain GPU preemption in two sentences.",
    "Write a haiku about Kubernetes.",
    "Why do we save checkpoints during training?",
]


def main():
    llm = LLM(model=MODEL)
    conversations = [[{"role": "user", "content": prompt}] for prompt in PROMPTS]
    outputs = llm.chat(conversations, SamplingParams(max_tokens=256))
    for prompt, output in zip(PROMPTS, outputs):
        print(f"### {prompt}\n{output.outputs[0].text}\n")


if __name__ == "__main__":
    main()
