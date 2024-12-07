# storygen experiment

This LLM experiment generates and ranks ideas for creative writing. It uses Ollama as its backing LLM engine.

## usage

```
$ python3 generate-and-rank.py --ideas 500
# ranked ideas output to final.log
```

## algorithm

### Idea Generation

The following prompt is passed to an LLM, and the output parsed into individual ideas.

> Write {BATCH_SIZE} one-sentence writing prompts for a short story. Be specific about the plot. Make some decisions. Be creative! Here are some adjectives to get you started: {3 ADJECTIVES}, and some feelings: {3 FEELINGS}.

The feelings and adjectives are sampled randomly from the text files in this repo. This introduces more interesting qualities to the response.

### Ranking

After ideas are generated, they are compared and scored using an elimination tournament:

1. Four ideas are selected at random from the available set.
2. An LLM is prompted to pick a winner, using a [meta prompting](https://www.promptingguide.ai/techniques/meta-prompting) approach
3. Repeat until all ideas have competed
4. The winners (1/4 of initial idea population) are advanced to the next round, and the process begins again.

When only a single winner emerges, the ranking process is complete and scores (number of wins) are reported for all ideas.

#### Meta Prompt 

Ideas are selected using the following prompt:

> You are an experienced editor, and you have a gut instinct for what will make a great story. First, analyze every one of the options by writing a few thoughts about each story idea. Label this section "Analysis". Then, consider which story has the most promise to be a compelling, engaging story when developed. Label this section with "Thinking and Evaluation". Finally, respond with your decisions on the top pick. Label this section "Final Decision". You should format your response this way: CHOICE(n) where n is a number. For example, CHOICE(1), or CHOICE(2), or CHOICE(3), CHOICE(4), and so on. Just make a single choice. The team will then approach the author to develop the story idea you selected. Base your decisions on careful comparison of the ideas, and choose the one that you think will be the most successful.
> Which of the following ideas should we pursue?