#!/usr/bin/env python3
import argparse
import random
import ollama
import logging
import json
import re
from collections import defaultdict

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


with open('adjectives.txt', 'r') as f:
    adjectives = f.read().splitlines()

with open('feelings.txt', 'r') as f:
    feelings = f.read().splitlines()

#model = 'dolphin-mistral'
model = 'wizardlm-uncensored'
llm = ollama.Client(host="127.0.0.1:11434")

IDEA_BATCH_SIZE = 5

def make_ideas():
    prompt = f"Write {IDEA_BATCH_SIZE} one-sentence writing prompts for a short story. Be specific about the plot. Make some decisions. Be creative! Here are some adjectives to get you started: " + ', '.join(random.sample(adjectives, 3)) + ", and some feelings: " + ', '.join(random.sample(feelings, 3)) + "."
    r = llm.generate(model=model, prompt=prompt)

    parsed = r["response"].split('\n')
    # remove any preceding numbers like 1. or 1)
    parsed = [re.sub(r'^\d+[.\)]*\s*', '', s) for s in parsed if s]

    with open('ideas.log', 'a') as f:
        f.write(json.dumps({
            "prompt": prompt,
            "raw": r,
            "ideas": parsed,
        }) + '\n')

    #logging.info(f"generated {len(parsed)} ideas")

    return parsed

def pick_one(ideas):
    formatted_ideas = [f"{i+1}. {s}" for i, s in enumerate(ideas)]
    system = "You are an experienced editor, and you have a gut instinct for what will make a great story. First, analyze every one of the options by writing a few thoughts about each story idea. Label this section \"Analysis\". Then, consider which story has the most promise to be a compelling, engaging story when developed. Label this section with \"Thinking and Evaluation\". Finally, respond with your decisions on the top pick. Label this section \"Final Decision\". You should format your response this way: CHOICE(n) where n is a number. For example, CHOICE(1), or CHOICE(2), or CHOICE(3), CHOICE(4), and so on. Just make a single choice. The team will then approach the author to develop the story idea you selected. Base your decisions on careful comparison of the ideas, and choose the one that you think will be the most successful."
    prompt = "Which of the following ideas should we pursue?\n" + '\n'.join(formatted_ideas)
    logging.info(f"picking from: {formatted_ideas}")

    r = llm.generate(model=model, prompt=prompt, system=system)
    txt = r["response"]
    logging.info(f"picked: {txt}")
    # find the number in the response
    choice = re.search(r'CHOICE\((\d)\)+', txt)
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

def tournament(ideas):
    size = 4
    scores = defaultdict(int)
    original_ideas = ideas[:]
    
    while len(ideas) > 1:
        logging.info(f"Evaluating over {len(ideas)} of {len(original_ideas)}")
        winners = []
        for i in range(0, len(ideas), size):
            if len(ideas) < size:
                ideas_subset = ideas
            else:
                ideas_subset = random.sample(ideas, size)
            winner = None
            while winner is None:
                winner = pick_one(ideas_subset)
                if winner is None:
                    logging.info("no winner picked, retrying")
            scores[winner] += 1
            winners.append(winner)
            logging.info(f"[{i//size}/{len(ideas)//size}], {len(winners)} advancing")
        ideas = winners

        with open('scores.log', 'a') as f:
            f.write(json.dumps(scores) + '\n')
        logging.info("round complete, appended scores to log")
    
    # Ensure all original ideas are included in the final ranking
    for idea in original_ideas:
        if idea not in scores:
            scores[idea] = 0
    
    #return sorted(original_ideas, key=lambda x: scores[x], reverse=True)
    # return the ideas sorted by score and their scores
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate and rank story ideas')
    parser.add_argument('--ideas', "-i", type=int, default=500, help='Number of ideas to generate')
    parser.add_argument('--verbose', "-v", action='store_true', help='Enable verbose logging')
    parser.add_argument('--ideas-from-log', action='store_true', help='Use ideas from last run log file')
    # TODO output directory option
    # TODO wire this up
    # parser.add_argument('--model', type=str, default='wizardlm-uncensored', help='Model to use')
    args = parser.parse_args()

    ideas = []
    if args.ideas_from_log:
        with open('ideas.log', 'r') as f:
            for line in f:
                data = json.loads(line)
                ideas.extend(data["ideas"])
        logging.info(f"loaded {len(ideas)} ideas from log")
    else:
        iters = args.ideas // IDEA_BATCH_SIZE
        while len(ideas) < args.ideas:
            new_ideas = make_ideas()
            ideas.extend(new_ideas)
            logging.info(f"generated {len(new_ideas)} ideas, total {len(ideas)} of {args.ideas}")
            if args.verbose and random.random() < 0.25:
                logging.info("random idea sample: " + random.choice(ideas))

    ranked = tournament(ideas)
    for idea, score in ranked:
        print(f"{score}\t{idea}")

    with open('final.log', 'a') as f:
        f.write(json.dumps(ranked) + '\n')