from __future__ import unicode_literals, print_function
import spacy
import sys, json, os
import pickle
from SourceCodeTools.proc.entity.util import inject_tokenizer, read_data, deal_with_incorrect_offsets
from spacy.gold import biluo_tags_from_offsets

from spacy.gold import GoldParse
from spacy.scorer import Scorer

import random
from pathlib import Path
import spacy
from spacy.util import minibatch, compounding


def evaluate(ner_model, examples):
    scorer = Scorer()
    for input_, annot in examples:
        doc_gold_text = ner_model.make_doc(input_)
        gold = GoldParse(doc_gold_text, entities=annot['entities'])
        pred_value = ner_model(input_)
        scorer.score(pred_value, gold)
    return {key: scorer.scores[key] for key in ['ents_p', 'ents_r', 'ents_f', 'ents_per_type']}
    return scorer.scores['ents_per_type']


def isvalid(nlp, text, ents):
    doc = nlp(text)
    tags = biluo_tags_from_offsets(doc, ents)
    if "-" in tags:
        return False
    else:
        return True


def main(TRAIN_DATA, TEST_DATA, model, output_dir=None, n_iter=100):
    nlp = spacy.load(model)  # load existing spaCy model

    print("dealing with inconsistencies")
    TRAIN_DATA = deal_with_incorrect_offsets(TRAIN_DATA, nlp)
    TEST_DATA = deal_with_incorrect_offsets(TEST_DATA, nlp)
    print("done dealing with inconsistencies")

    # create the built-in pipeline components and add them to the pipeline
    # nlp.create_pipe works for built-ins that are registered with spaCy
    if "ner" not in nlp.pipe_names:
        ner = nlp.create_pipe("ner")
        nlp.add_pipe(ner, last=True)
    # otherwise, get it so we can add labels
    else:
        ner = nlp.get_pipe("ner")

    # add labels
    for _, annotations in TRAIN_DATA:
        for ent in annotations.get("entities"):
            ner.add_label(ent[2])

    # get names of other pipes to disable them during training
    other_pipes = [pipe for pipe in nlp.pipe_names if pipe != "ner"]
    with nlp.disable_pipes(*other_pipes):  # only train NER
        # reset and initialize the weights randomly – but only if we're
        # training a new model
        # if model is None:
        nlp.begin_training()
        for itn in range(n_iter):
            random.shuffle(TRAIN_DATA)
            losses = {}
            # batch up the examples using spaCy's minibatch
            batches = minibatch(TRAIN_DATA, size=compounding(4.0, 32.0, 1.001))
            for batch in batches:
                texts, annotations = zip(*batch)
                nlp.update(
                    texts,  # batch of texts
                    annotations,  # batch of annotations
                    drop=0.5,  # dropout - make it harder to memorise data
                    losses=losses,
                )
            print(f"{itn}:")
            print("\tLosses", losses)
            score = evaluate(nlp, TEST_DATA)
            if not os.path.isdir("models"):
                os.mkdir("models")
            nlp.to_disk(os.path.join("models", f"model_{itn}"))
            print("\t", score)



if __name__ == "__main__":
    model_path = sys.argv[1]
    data_path = sys.argv[2]
    output_dir = "model-final-ner"
    n_iter = 90

    # ent_types = []
    # for _, e in TRAIN_DATA:
    #     ee = [ent[2] for ent in e['entities']]
    #     ent_types += ee

    TRAIN_DATA, TEST_DATA = read_data(data_path, normalize=True)
    main(TRAIN_DATA, TEST_DATA, model=model_path,output_dir=output_dir, n_iter=n_iter)