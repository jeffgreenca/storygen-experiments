#!/usr/bin/env python3
import argparse
import random
import ollama
import logging
import json
import re
import os

def _make_logger():
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    # also log to file
    file_handler = logging.FileHandler('generate-and-rank.log')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    return logger

logging = _make_logger()

class LLM:
    def __init__(self, host="127.0.0.1:11434", model="wizardlm-uncensored"):
        self._llm = ollama.Client(host=host)
        self._model = model

    def generate(self, prompt, system=""):
        return self._llm.generate(model=self._model, prompt=prompt, system=system)

class IdeaGenerator:
    def __init__(self, output_dir='.', llm=None):
        self._output_dir = output_dir
        self._llm = llm

        with open('adjectives.txt', 'r') as f:
            self._adjectives = f.read().splitlines()

        with open('feelings.txt', 'r') as f:
            self._feelings = f.read().splitlines()

    def make_ideas(self, batch_size=5):
        prompt = f"Write {batch_size} one-sentence writing prompts for a short story. Be specific about the plot. Make some decisions. Be creative! Here are some adjectives to get you started: " + ', '.join(random.sample(self._adjectives, 3)) + ", and some feelings: " + ', '.join(random.sample(self._feelings, 3)) + "."
        r = self._llm.generate(prompt)

        parsed = r["response"].split('\n')
        # remove any preceding numbers like 1. or 1)
        parsed = [re.sub(r'^\d+[.\)]*\s*', '', s) for s in parsed if s]

        with open(os.path.join(self._output_dir, 'ideas.log'), 'a') as f:
            f.write(json.dumps({
                "prompt": prompt,
                "raw": r,
                "ideas": parsed,
            }) + '\n')

        return parsed

class IdeaPicker:
    def __init__(self, output_dir='.', llm=None):
        self._llm = llm
        self._output_dir = output_dir

    def _pick_one(self, ideas):
        formatted_ideas = [f"{i+1}. {s}" for i, s in enumerate(ideas)]
        system = "You are an experienced editor, and you have a gut instinct for what will make a great story. First, analyze every one of the options by writing a few thoughts about each story idea. Label this section \"Analysis\". Then, consider which story has the most promise to be a compelling, engaging story when developed. Label this section with \"Thinking and Evaluation\". Finally, respond with your decisions on the top pick. Label this section \"Final Decision\". You should format your response this way: CHOICE(n) where n is a number. For example, CHOICE(1), or CHOICE(2), or CHOICE(3), CHOICE(4), and so on. Just make a single choice. The team will then approach the author to develop the story idea you selected. Base your decisions on careful comparison of the ideas, and choose the one that you think will be the most successful."
        prompt = "Which of the following ideas should we pursue?\n" + '\n'.join(formatted_ideas)
        logging.info(f"picking from: {formatted_ideas}")

        r = self._llm.generate(prompt=prompt, system=system)
        txt = r["response"]
        logging.info(f"picked: {txt}")
        # find the number in the response
        choice = re.search(r'CHOICE\((\d+)\)', txt)
        if choice is None:
            logging.info(f"no choice found in response: {txt}")
            return None
        choice_group = choice.group(1)
        if choice_group is None:
            logging.info(f"no choice group found in response (no group): {txt}")
            return None
        # if choice is out of bounds, return None
        choice_int = int(choice_group) - 1
        if choice_int < 0 or choice_int >= len(ideas):
            return None
        # return the chosen idea
        return ideas[choice_int]

    def _pick_one_with_retry(self, ideas, max_retries=5):
        for _ in range(max_retries):
            choice = self._pick_one(ideas)
            if choice is not None:
                return choice
        return None

    def rank(self, ideas, max_compare_together=4):
        # we could use a defaultdict here, but we want to ensure all ideas are included in the final ranking,
        # even ideas that had a zero score.
        scores = {idea: 0 for idea in ideas}
        round_number = 1

        while len(ideas) > 1:
            logging.info(f"Round {round_number}: Evaluating {len(ideas)} ideas")
            winners = []
            random.shuffle(ideas)
            
            for i in range(0, len(ideas), max_compare_together):
                ideas_subset = ideas[i:i+max_compare_together]
                best = None
                if len(ideas_subset) == 1:
                    logging.info(f"only one idea left in this group, automatically advancing: {ideas_subset[0]}")
                    best = ideas_subset[0]
                else:
                    # normal flow
                    best = self._pick_one_with_retry(ideas_subset)
                if best is None:
                    logging.info(f"could not pick a winner from {ideas_subset}")
                    continue
                try:
                    scores[best] += 1
                    winners.append(best)
                except KeyError:
                    logging.warning(f"winner {best} not in scores, skipping")
            
            ideas = winners
            round_number += 1

            with open(os.path.join(self._output_dir, 'scores.log'), 'a') as f:
                f.write(json.dumps(scores) + '\n')
            logging.info(f"round {round_number} complete, {len(ideas)} ideas continue to next round")
        
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate and rank story ideas')
    parser.add_argument('--host', type=str, default="127.0.0.1:11434", help='OLLAMA host')
    parser.add_argument('--model', type=str, default='wizardlm-uncensored', help='LLM model to use for generation')
    parser.add_argument('--output_dir', '-o', type=str, default='.', help='Output directory')
    parser.add_argument('--verbose', "-v", action='store_true', help='Enable verbose logging')
    parser.add_argument('--idea-batch-size', "-b", type=int, default=5, help='Number of ideas to generate at a time')
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--generate-ideas', "-g", type=int, default=500, help='Number of ideas to generate')
    group.add_argument('--ideas-from-log', '-i', type=str, help='Skip idea generation, and read from specified log file')
    args = parser.parse_args()

    llm = LLM(model=args.model, host=args.host)
    idea_generator = IdeaGenerator(output_dir=args.output_dir, llm=llm)
    idea_picker = IdeaPicker(output_dir=args.output_dir, llm=llm)

    ideas = []
    if args.ideas_from_log:
        with open(args.ideas_from_log, 'r') as f:
            for line in f:
                data = json.loads(line)
                ideas.extend(data["ideas"])
        logging.info(f"loaded {len(ideas)} ideas from log")
    else:
        iters = args.generate_ideas // args.idea_batch_size
        while len(ideas) < args.generate_ideas:
            new_ideas = idea_generator.make_ideas(batch_size=args.idea_batch_size)
            ideas.extend(new_ideas)
            logging.info(f"generated {len(new_ideas)} ideas, total {len(ideas)} of {args.generate_ideas}")
            if args.verbose and random.random() < 0.25:
                logging.info("random idea sample: " + random.choice(ideas))

    ranked = idea_picker.rank(ideas)
    for idea, score in ranked:
        print(f"{score}\t{idea}")

    with open(os.path.join(args.output_dir, 'final.log'), 'a') as f:
        f.write(json.dumps(ranked) + '\n')