from __future__ import unicode_literals, print_function
import spacy
import sys, json
import pickle
from custom_tokenizer import inject_tokenizer
from spacy.gold import biluo_tags_from_offsets

model_path = sys.argv[1]
data_path = sys.argv[2]
output_dir = "model-final-ner"
n_iter = 30

def isvalid(nlp, text, ents):
    doc = nlp(text)
    tags = biluo_tags_from_offsets(doc, ents)
    if "-" in tags:
        return False
    else:
        return True


import random
from pathlib import Path
import spacy
from spacy.util import minibatch, compounding

TRAIN_DATA = []
with open(data_path, "r") as data:
    for line in data:
        entry = json.loads(line)
        TRAIN_DATA.append([entry['text'], {'entities': entry['ents']}])
        TRAIN_DATA[-1][1]['entities'] = [(int(e[0]), int(e[1])-1, e[2]) for e in TRAIN_DATA[-1][1]['entities']]


ent_types = []
for _,e in TRAIN_DATA:
    ee = [ent[2] for ent in e['entities']]
    ent_types += ee


def main(model=None, output_dir=None, n_iter=100):
    """Load the model, set up the pipeline and train the entity recognizer."""
    # if model is not None:
    #     nlp = spacy.load(model)  # load existing spaCy model
    #     print("Loaded model '%s'" % model)
    # else:
    #     nlp = spacy.blank("en")  # create blank Language class
    #     print("Created blank 'en' model")

    nlp = spacy.blank("en")
    nlp = inject_tokenizer(nlp)

    for text, ent in TRAIN_DATA:
        doc = nlp(text)
        entities = ent['entities']
        tags = biluo_tags_from_offsets(doc, entities)
        print(text)
        print(entities, tags)
        if text.startswith("def _bundle_extensions(objs, resources)"):
            pass
        # if "-" in tags:
        #     for t in doc:
        #         if t.is_space: continue
        #         print(t, tags[t.i])
        #         if t.text == '.':
        #             print()

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
        if model is None:
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
            print("Losses", losses)

    # test the trained model
    for text, _ in TRAIN_DATA:
        doc = nlp(text)
        print("Entities", [(ent.text, ent.label_) for ent in doc.ents])
        print("Tokens", [(t.text, t.ent_type_, t.ent_iob) for t in doc])

    # save model to output directory
    if output_dir is not None:
        output_dir = Path(output_dir)
        if not output_dir.exists():
            output_dir.mkdir()
        nlp.to_disk(output_dir)
        print("Saved model to", output_dir)

        # test the saved model
        print("Loading from", output_dir)
        nlp2 = spacy.load(output_dir)
        for text, _ in TRAIN_DATA:
            doc = nlp2(text)
            print("Entities", [(ent.text, ent.label_) for ent in doc.ents])
            print("Tokens", [(t.text, t.ent_type_, t.ent_iob) for t in doc])


if __name__ == "__main__":
    # en_core_web_sm
    main(model=model_path,output_dir=output_dir, n_iter=n_iter)
    # plac.call(main)

    # Expected output:
    # Entities [('Shaka Khan', 'PERSON')]
    # Tokens [('Who', '', 2), ('is', '', 2), ('Shaka', 'PERSON', 3),
    # ('Khan', 'PERSON', 1), ('?', '', 2)]
    # Entities [('London', 'LOC'), ('Berlin', 'LOC')]
    # Tokens [('I', '', 2), ('like', '', 2), ('London', 'LOC', 3),
    # ('and', '', 2), ('Berlin', 'LOC', 3), ('.', '', 2)]