from rdflib import *
from SPARQLWrapper import *
import sys
import json
import re
import shlex
import subprocess
import urllib2

original_out = sys.stdout
prop_val_count = {}
ans_dict = {}
parameter_list = ['value', 'total_values', 'frequency', 'blacklisted', 'is_onto', 'special_char',
                  'no_of_words', 'has_range', 'has_comment', 'value_relevant',
                  'google_keypress', 'google_location', 'special_datatype',
                  'is_of_relation', 'score', 'label']


def get_label(prop):
    '''
    Function to covert camelCase into distinct words.
    Example: string "wikiPageID" is returned as a string "wiki Page ID" using RegEx.
    '''
    prop = prop.split('/')[-1]
    prop = re.sub(
        r'((?<=[a-z])[A-Z]|(?<!\A)[A-Z](?=[a-z]))', r' \1', prop)
    return prop


def get_resource_type(results):
    '''
    Computes the resource type of the resource.
    Example:For resource =' Iron_Maiden', returns resource_type = 'http://dbpedia.org/ontology/Organisation'
    '''
    resource_type = None
    for result in results["results"]["bindings"]:
        prop = result["prop"]["value"]
        value = result["value"]["value"]
        if "#type" in prop:
            if "dbpedia.org/ontology" in value:
                resource_type = value
    if resource_type is None:
        return "http://www.w3.org/2002/07/owl#Thing"
    else:
        return resource_type


def blacklisted(prop):
    '''
    Function to check whether the particular prop is blacklisted,
    by checking if it has "wiki" or "image" or "same As" is in its name or the length is less than three,
     making the prop relevant
    '''
    if " id" in prop or "PrimaryTopicOf" in prop or "wiki" in prop or "image" in prop or "same As" in prop or "Photo" in prop or len(prop) < 3:
        return 1
    else:
        return 0


def is_onto(prop):
    '''
    Function checks if the prop type is ontology or not.
    '''
    if "ontology" in prop:
        return 1
    else:
        return 0


def doesnt_contain_special_chars(prop):
    '''
    Function which returns 0 if prop has chars other than letters and space.
    '''
    pattern = re.compile("^[a-zA-Z\s]*$")
    if pattern.match(prop):
        return 1
    else:
        return 0


def no_of_words(prop):
    '''
    Function to count number of words in the prop name.
    Returns the inverse of (count of spaces encountered plus 1).
    '''
    return 1.0 / float(prop.count(' ') + 1)  # returns inverse of no of words


def prop_has_range_or_comment(prop_value):
    '''
    Function to check whether the property has 'range' or 'comment' attribute associated with it.
    '''
    # return (0, 0)
    has_comment = 0
    has_range = 0
    prop = prop_value['prop']

    sparql = SPARQLWrapper("http://dbpedia.org/sparql")
    query1 = """
    select distinct ?prop ?value where {
      <""" + prop + """> ?prop ?value }
      """

    sparql.setQuery(query1)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    for result in results["results"]["bindings"]:
        prop = result["prop"]["value"]
        if "range" in prop:
            has_range = 1
        if "comment" in prop:
            has_comment = 1

    return (has_range, has_comment)


def value_relevant(prop_value):
    '''
    Function which analyzes the value for files or images making the property less relevant.
    '''
    value = prop_value['value']
    if "File" in value or "wordnet" in value or ".ogg" in value or ".svg" in value or ".jpg" in value or ".png" in value:
        return 0
    else:
        return 1


def google_autocomplete_ranker(resource, prop):
    '''
    Function which counts the number of characters from prop name needed to be pressed so that the prop is
    suggested by Google auto-complete pertaining to the current resource.

    Returns total key-presses required and the location at which its suggested.
    '''
    # return (0, 0)
    resource = resource.replace(" ", "_")

    prop = prop.lower()
    google_keypresses = 0
    success = 0
    suggest_location = 1

    while (google_keypresses <= len(prop) and google_keypresses <= 4):

        temp_string = prop[0:google_keypresses]
        suggest_location = 1

        # base_url to request
        request_url = 'http://google.com/complete/search?client=chrome&q='
        request_string = request_url + resource + '_' + \
            temp_string.replace(" ", "_")  # build complete query url
        content = urllib2.urlopen(request_string).read()
        content = unicode(content, errors='replace')  # handle utf-8 errors
        content_json = json.loads(content)  # save response as list

        for key, val in enumerate(content_json[1]):
            suggest_location += 1
            if prop in val:
                success = 1
                break

        if success == 1:
            break

        google_keypresses += 1

    if success == 0:
        suggest_location = 0
    else:
        suggest_location = 1.0 / suggest_location

    return (1.0 / (google_keypresses + 1), suggest_location)


def handle_is_of_relations(resource, resource_type, total_pages):

    sparql = SPARQLWrapper("http://dbpedia.org/sparql")

    query1 = """
    select  ?prop ?value where {
    ?value ?prop <http://dbpedia.org/resource/""" + resource + """>  }
    """

    sparql.setQuery(query1)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    for result in results["results"]["bindings"]:
        prop = result["prop"]["value"]
        value = result["value"]["value"]
        cleaned_property_label = get_label(prop)

        if blacklisted(cleaned_property_label):
            continue

        if "ontology" not in prop and "property" not in prop and "subject" not in prop:
            continue

        if prop in ans_dict:
            ans_dict[prop].setdefault('value', []).append(value)
            prop_val_count[prop] += 1
            ans_dict[prop]['is_of_relation'] = 1
            continue

        prop_info = dict.fromkeys(parameter_list, 0)
        prop_info['score'] = 0
        prop_info['value'] = []

        if "xml:lang" not in result["value"] or 'en' in result["value"]["xml:lang"]:
            prop_value = {}
            prop_value['prop'] = prop
            prop_value['value'] = value

            if prop in prop_val_count:
                prop_val_count[prop] += 1

            else:
                prop_val_count[prop] = 1

            cleaned_property_label = get_label(prop)
            prop_info['label'] = cleaned_property_label

            prop_info.setdefault('value', []).append(value)
            prop_info['blacklisted'] = 0
            '''
            if prop_info['blacklisted']:
                ans_dict[prop] = prop_info
                continue
            '''
            google_autosuggest = google_autocomplete_ranker(
                resource, cleaned_property_label)
            prop_info['is_onto'] = is_onto(prop)
            prop_info['special_char'] = doesnt_contain_special_chars(
                cleaned_property_label)
            prop_info['no_of_words'] = no_of_words(cleaned_property_label)
            range_comment = prop_has_range_or_comment(prop_value)
            prop_info['has_range'] = range_comment[0]
            prop_info['has_comment'] = range_comment[1]
            prop_info['value_relevant'] = value_relevant(prop_value)
            prop_info['special_datatype'] = is_special_datatype(result)
            prop_info['google_keypress'] = google_autosuggest[0]
            prop_info['google_location'] = google_autosuggest[1]
            prop_info['is_of_relation'] = 1
            prop_info['frequency'] = count_freq(
                resource_type, prop) / float(total_pages)
        ans_dict[prop] = prop_info


def is_special_datatype(result):
    '''
    Function to check whether value has a special data type like date, etc.
    TODO: Determine more special relevant data types.
    '''
    if "datatype" in result['value']:
        value_datatype = result['value']['datatype']

        if 'date' in value_datatype:
            return 1
        else:
            return 0

    return 0


def count_freq(resource_type, prop):
    '''
    Function which counts how many times has the property appeared w.r.t. the resource type.
    '''
    freq = 0
    sparql = SPARQLWrapper("http://dbpedia.org/sparql")

    query1 = """
    SELECT COUNT(DISTINCT ?entity)
    WHERE { ?entity <""" + prop + """> ?value.
    ?entity <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <""" + resource_type + """> }
    """

    sparql.setQuery(query1)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    for result in results["results"]["bindings"]:
        freq = int(result["callret-0"]["value"])

    return freq


def total_pages_for_type(resource_type):
    '''
    Function which returns the total number of resources belonging to given resource type.
    '''
    freq = 0
    sparql = SPARQLWrapper("http://dbpedia.org/sparql")

    query1 = """
    SELECT COUNT(DISTINCT ?entity)
    WHERE { ?entity <http://dbpedia.org/ontology/wikiPageID> ?value.
    ?entity <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <""" + resource_type + """> }
    """

    sparql.setQuery(query1)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()

    for result in results["results"]["bindings"]:
        freq = int(result["callret-0"]["value"])

    return freq


normalized_labels = []


def start(resource):

    sparql = SPARQLWrapper("http://dbpedia.org/sparql")
    query1 = """
    select distinct ?prop ?value
    where {
    <http://dbpedia.org/resource/""" + resource + """> ?prop ?value }
      """

    sparql.setQuery(query1)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    resource_type = get_resource_type(results)
    total_pages = total_pages_for_type(resource_type)

    for result in results["results"]["bindings"]:

        prop = result["prop"]["value"]
        value = result["value"]["value"]
        cleaned_property_label = get_label(prop)

        if "ontology" not in prop and "property" not in prop and "subject" not in prop:
            continue

        prop_info = dict.fromkeys(parameter_list, 0)
        prop_info['score'] = 0
        prop_info['value'] = []

        if "xml:lang" not in result["value"] or 'en' in result["value"]["xml:lang"]:

            prop_value = {}
            prop_value['prop'] = prop
            prop_value['value'] = value

            if prop in prop_val_count:
                prop_val_count[prop] += 1
            else:

                normalized_label = cleaned_property_label.lower().replace(
                    ' ', '')

                if normalized_label in normalized_labels:
                    continue

                normalized_labels.append(normalized_label)
                prop_val_count[prop] = 1

            if prop in ans_dict:
                ans_dict[prop].setdefault('value', []).append(value)
                continue

            prop_info['label'] = cleaned_property_label

            prop_info.setdefault('value', []).append(value)
            prop_info['blacklisted'] = 0

            '''
            if prop_info['blacklisted']:
                ans_dict[prop] = prop_info
                continue
            '''

            google_autosuggest = google_autocomplete_ranker(
                resource, cleaned_property_label)
            prop_info['is_onto'] = is_onto(prop)
            prop_info['special_char'] = doesnt_contain_special_chars(
                cleaned_property_label)
            prop_info['no_of_words'] = no_of_words(cleaned_property_label)
            range_comment = prop_has_range_or_comment(prop_value)
            prop_info['has_range'] = range_comment[0]
            prop_info['has_comment'] = range_comment[1]
            prop_info['value_relevant'] = value_relevant(prop_value)
            prop_info['special_datatype'] = is_special_datatype(result)
            prop_info['google_keypress'] = google_autosuggest[0]
            prop_info['google_location'] = google_autosuggest[1]
            prop_info['is_of_relation'] = 0
            prop_info['frequency'] = count_freq(
                resource_type, prop) / float(total_pages)
        ans_dict[prop] = prop_info

    #handle_is_of_relations(resource, resource_type,  total_pages)

    for prop, count in prop_val_count.iteritems():
        ans_dict[prop]['total_values'] = (1.0 - 1.0 / count)
        #score = raw_input("Enter score for: " + prop + " (from 1-5) \n")
        ans_dict[prop]['score'] = 0


def rank_properties(resource):
    prop_val_count.clear()
    ans_dict.clear()
    del normalized_labels[:]
    res = resource
    start(res)
    open_file = res + "_test.txt"
    sys.stdout = open(open_file, 'w')

    '''
    jsonfile = json.dumps(ans_dict).encode('utf-8')
    infoFromJson = json.loads(jsonfile)
    print json2html.convert(json=infoFromJson).encode('utf-8')
    end = datetime.datetime.now()
    print ("Total Time taken: " + str(end - stt))
    '''
    for prop, count in prop_val_count.iteritems():
        print (str(ans_dict[prop]['score']) + " qid:1" + " 1:" + str(ans_dict[prop]['frequency']) +
               " 2:" + str(ans_dict[prop]['is_of_relation']) +
               " 3:" + str(ans_dict[prop]['is_onto']) + " 4:" + str(ans_dict[prop]['has_range']) +
               " 5:" + str(ans_dict[prop]['has_comment']) + " 6:" + str(ans_dict[prop]['total_values']) +
               " 7:" + str(ans_dict[prop]['google_keypress']) + " 8:" + str(ans_dict[prop]['google_location']) +
               " 9:" + str(ans_dict[prop]['value_relevant']) + " 10:" + str(ans_dict[prop]['blacklisted']) +
               " 11:" + str(ans_dict[prop]['special_char']) + " 12:" + str(ans_dict[prop]['no_of_words']) +
               " 13:" + str(ans_dict[prop]['special_datatype']) + " # " + prop)

    sys.stdout = original_out
    ans_list = []
    del ans_list[:]

    prop_file = res + '_test.txt'
    score_file = res + '_score.txt'

    cmd = "java -jar RankLib-2.1-patched.jar -load new_model.txt -rank \"" + \
        prop_file + "\" -score \"" + score_file + "\""
    args = shlex.split(cmd)
    p = subprocess.call(args)

    # time.sleep(10)
    with open(prop_file) as f:
        lines = f.readlines()

    for line in lines:
        prop = line.split('# ')[-1]
        prop = prop[0:len(prop) - 1]
        content = [0, prop]
        ans_list.append(content)
        # print prop

    with open(score_file) as f:
        lines = f.readlines()

    i = 0
    for line in lines:
        score = re.findall(r"[-+]?\d*\.\d+|\d+", line)[-1]
        ans_list[i][0] = score
        i += 1

    ans_list.sort(cmp=None, key=None, reverse=True)

    tot_val = len(ans_list)
    tot = '"total": "' + str(tot_val) + '", '
    ans = '{' + tot + '  "error": "0" , "resources": ['

    res = ""
    i = 1
    for x in ans_list:

        val_string = ""
        for v in ans_dict[x[1]]['value']:
            v = v.replace('\"', '')
            val_string += """{ "value": \"""" + v +  """\"},"""

        val_string = val_string[0:-1]
        res += """
        {
    "rank": \"""" + str(i) + """\",
    "property": \"""" + str(x[1]) + """\",
    "score": \"""" + str(x[0]) + """\",
    "label": \"""" + str(ans_dict[x[1]]['label']) + """\",
    "is_of": \"""" + str(ans_dict[x[1]]['is_of_relation']) + """\",
    "values": [ """ + val_string + """ ]



    },"""
        i += 1

    ans += res
    ans = ans[0:-1]
    ans += ']}'
    ans = ans.replace('\\', '')
    # print ans

    json_obj = json.loads(ans, strict=False)
    ans = json.dumps(json_obj, indent=4)
    return ans


print rank_properties("Facebook")
