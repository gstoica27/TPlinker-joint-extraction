from stanfordcorenlp import StanfordCoreNLP
import os
import json
import numpy as np
import stanza
from collections import defaultdict

def load_json(filepath, by_line=True):
    data = []
    with open(filepath, 'r') as handle:
        if by_line:
            for line in handle:
                data.append(
                    json.loads(line)
                )
        else:
            data = json.load(handle)
    return data

def parse_corpus(text_file):
    observed_triples = set()
    question2answers = defaultdict(lambda: set())
    corpus_components = {'sentences': [], 'subjects': [], 'objects': [],
                         'subject_ids': [], 'object_ids': [], 'relations': []}
    with open(text_file, 'r') as handle:
        instances = handle.readlines()
        for txt_instance in instances:
            instance = eval(txt_instance)
            corpus_components['sentences'].append(instance['text'])
            corpus_components['subjects'].append(instance['h']['name'])
            corpus_components['objects'].append(instance['t']['name'])
            corpus_components['subject_ids'].append(instance['h']['id'])
            corpus_components['object_ids'].append(instance['t']['id'])
            corpus_components['relations'].append(instance['relation'])
            triple = (instance['h']['id'], instance['relation'], instance['t']['id'])
            question = (instance['h']['id'], instance['relation'])
            observed_triples.add(triple)
            question2answers[question].add(instance['t']['id'])
    return {'components': corpus_components,
            'triples': observed_triples,
            'question2answers': question2answers}



def extract_nlp_components(text_file, stanza_nlp, core_nlp):
    components = []
    with open(text_file, 'r') as handle:
        raw_text = handle.readlines()
        for counter, i in enumerate(range(0, len(raw_text), 4)):
            sentence_id, sentence = raw_text[i].split('\t')
            sentence = sentence.strip().strip('"')
            tokens = core_nlp.word_tokenize(sentence)
            # SUBJECT/OBJECT SPANS
            subject_start = tokens.index('<e1>')
            subject_end = tokens.index('</e1>') - 2
            object_start = tokens.index('<e2>') - 2
            object_end = tokens.index('</e2>') - 4
            sentence = sentence.replace("<e1>", "").\
                replace("</e1>", "").\
                replace("<e2>", "").\
                replace("</e2>", "")
            parsed_tokens = core_nlp.word_tokenize(sentence)
            # NER CALCULATION
            _, token_ners = zip(*core_nlp.ner(sentence))
            token_ners = list(token_ners)
            subject_ners = np.unique(np.array(token_ners)[subject_start: subject_end + 1])
            object_ners = np.unique(np.array(token_ners)[object_start:object_end + 1])
            subject_ner = compute_entity_ner(subject_ners)
            object_ner = compute_entity_ner(object_ners)
            # POS CALCULATION
            _, token_pos = zip(*core_nlp.pos_tag(sentence))
            token_pos = list(token_pos)
            # DEPENDENCY TREE
            # stanza_tokens = stanza_nlp(sentence).sentences[0].words
            # token_deprel, token_head = get_deprel_and_head(stanza_tokens)
            token_deprel, token_head = extract_dependencies(sentence, core_nlp=core_nlp)
            # RELATION
            relation = raw_text[i+1].strip()
            # QUALITY CHECK
            assert (len(parsed_tokens) == len(token_ners))
            assert (len(parsed_tokens) == len(token_pos))
            assert (len(parsed_tokens) == len(token_deprel))
            assert (len(parsed_tokens) == len(token_head))
            assert (subject_start >= 0)
            assert (subject_end < len(parsed_tokens))
            assert (object_start >= 0)
            assert (object_end < len(parsed_tokens))

            sample = {
                'id': str(int(sentence_id) - 1),
                'token': parsed_tokens,
                'subj_start': subject_start,
                'subj_end': subject_end,
                'obj_start': object_start,
                'obj_end': object_end,
                'subj_type': subject_ner,
                'obj_type': object_ner,
                'stanford_pos': token_pos,
                'stanford_ner': token_ners,
                'stanford_deprel': token_deprel,
                'stanford_head': token_head,
                'relation': relation
            }
            components.append(sample)
            if counter > 0 and counter % int(len(raw_text) / 40) == 0:
                prop_finished = counter / (len(raw_text) / 40)
                print(f'Finished {prop_finished}')

        return components

def extract_dependencies(sentence, core_nlp):
    dependencies = core_nlp.dependency_parse(sentence)
    deprels = [''] * len(dependencies)
    heads = [0] * len(dependencies)
    for node in dependencies:
        deprel, head, idx = node
        deprels[idx-1] = deprel
        heads[idx-1] = head
    return deprels, heads

def get_deprel_and_head(stanza_tokens):
    deprel = []
    head = []
    for token in stanza_tokens:
        deprel.append(token.deprel)
        head.append(token.head)
    return deprel, head

def load_data(data_file):
    with open(data_file, 'r') as handle:
        return json.load(handle)

def compute_entity_ner(ners):
    entity_ner = None
    for candidate_ner in ners:
        if entity_ner is None:
            entity_ner = candidate_ner
        elif candidate_ner != 'O' and entity_ner == 'O':
            entity_ner = candidate_ner
    return entity_ner

def augment_data(data, sentences, nlp):
    new_data = []
    for sample in data:
        # sample id is zero indexed but sentences are 1 indexed
        sample_id = str(int(sample['id']) + 1)
        sentence = sentences[sample_id]
        tokens = sample['token']
        # sentence = ' '.join(tokens)
        token_ners = nlp.ner(sentence)
        # Add NER
        ners = []
        for token, ner in token_ners:
            if ner.isupper():
                ners.append(ner)
            else:
                ners.append('O')
        assert (len(ners) == len(tokens))
        sample['stanford_ner'] = ners
        ss, se = sample['subj_start'], sample['subj_end']
        os, oe = sample['obj_start'], sample['obj_end']

        subject_ners = np.unique(np.array(ners)[ss: se+1])
        object_ners = np.unique(np.array(ners)[os:oe+1])

        subject_ner = compute_entity_ner(subject_ners)
        object_ner = compute_entity_ner(object_ners)
        sample['subj_type'] = subject_ner
        sample['obj_type'] = object_ner
        new_data.append(sample)
    return new_data

if __name__ == '__main__':
    # stanza.download('en')
    # stanza_nlp = stanza.Pipeline('en')
    core_nlp = StanfordCoreNLP(r'/Users/georgestoica/Desktop/stanford-corenlp-4.0.0')

    data_dir = '/Users/georgestoica/Desktop/Research/TPlinker-joint-extraction/ori_data/nyt_raw'
    train_file = os.path.join(data_dir, 'raw_train.json')
    dev_file = os.path.join(data_dir, 'raw_valid.json')
    test_file = os.path.join(data_dir, 'raw_test.json')

    train_metadata = parse_corpus(train_file)
    dev_metadata = parse_corpus(dev_file)
    test_meta_data = parse_corpus(test_file)
    print('Extracted!')
    # raw_semevel_dir = '/Users/georgestoica/Desktop/SemEval2010_task8_all_data'
    # train_file = os.path.join(raw_semevel_dir,
    #                           'SemEval2010_task8_training',
    #                           'TRAIN_FILE.TXT')
    # test_file = os.path.join(raw_semevel_dir,
    #                          'SemEval2010_task8_testing_keys',
    #                          'TEST_FILE_FULL.TXT')
    #
    # train_data = extract_nlp_components(train_file, stanza_nlp=stanza_nlp, core_nlp=core_nlp)
    # train_save_file = os.path.join(data_dir, 'train_sampled.json')
    # json.dump(train_data, open(train_save_file, 'w'))
    # test_data = extract_nlp_components(test_file, stanza_nlp=stanza_nlp, core_nlp=core_nlp)
    # test_save_file = os.path.join(data_dir, 'test_new.json')
    # json.dump(test_data, open(test_save_file, 'w'))

    core_nlp.close()