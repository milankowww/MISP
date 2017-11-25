#!/usr/bin/env python3
#    Copyright (C) 2017 CIRCL Computer Incident Response Center Luxembourg (smile gie)
#    Copyright (C) 2017 Christian Studer
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys, json, os, datetime, re
import pymisp
from stix2 import *
from misp2stix2_dictionaries import *

namespace = ['https://github.com/MISP/MISP', 'MISP']

not_implemented_attributes = ['yara', 'pattern-in-traffic', 'pattern-in-memory']

non_indicator_attributes = ['text', 'comment', 'other', 'link', 'target-user', 'target-email',
                            'target-machine', 'target-org', 'target-location', 'target-external',
                            'vulnerability', 'attachment']

noChangesTypes = ['', '']

def saveFile(args, pathname, package):
    filename = args[1] + '.out'
    with open(filename, 'w') as f:
        f.write(json.dumps(package, cls=base.STIXJSONEncoder))

# converts timestamp to the format used by STIX
def getDateFromTimestamp(timestamp):
    return datetime.datetime.utcfromtimestamp(timestamp).isoformat() + "+00:00"

def setIdentity(event, SDOs):
    org = event.Orgc
    identity_id = 'identity--{}'.format(org['uuid'])
    identity = Identity(type="identity", id=identity_id,
                        name=org["name"], identity_class="organization")
    SDOs.append(identity)
    return identity_id

def readAttributes(event, identity, object_refs, external_refs):
    attributes = []
    descFilename = os.path.join(pymisp.__path__[0], 'data/describeTypes.json')
    descFile = open(descFilename, 'r')
    types = json.loads(descFile.read())['result']
    for attribute in event.attributes:
        attr_type = attribute.type
        if attr_type in non_indicator_attributes:
            if attr_type == "link":
                handleLink(attribute, external_refs)
            elif attr_type in ('text', 'comment', 'other'):
                addCustomObject(object_refs, attributes, attribute, identity)
            else:
                handleNonIndicatorAttribute(object_refs, attributes, attribute, identity)
        else:
            mapping = types['category_type_mappings']
            if attr_type in mapping['Person']:
                addIdentity(object_refs, attributes, attribute, identity, 'individual')
            elif attr_type in mispTypesMapping:
                if attribute.to_ids:
                    handleIndicatorAttribute(object_refs, attributes, attribute, identity)
                else:
                    addObservedData(object_refs, attributes, attribute, identity)
            else:
                addCustomObject(object_refs, attributes, attribute, identity)
    galaxy = False
    try:
        if event.Galaxy:
            galaxy = True
    except:
        pass
    if galaxy:
        galaxies = event.Galaxy
        for galaxy in galaxies:
            galaxyType = galaxy['type']
            if 'attack-pattern' in galaxyType:
                addAttackPattern(object_refs, attributes, galaxy, identity)
            elif 'course' in galaxyType:
                addCourseOfAction(object_refs, attributes, galaxy, identity)
            elif 'intrusion' in galaxyType:
                addIntrusionSet(object_refs, attributes, galaxy, identity)
            elif 'ware' in galaxyType:
                addMalware(object_refs, attributes, galaxy, identity)
            elif galaxyType in ['threat-actor', 'microsoft-activity-group']:
                addThreatActor(object_refs, attributes, galaxy, identity)
            elif galaxyType in ['rat', 'exploit-kit'] or 'tool' in galaxyType:
                addTool(object_refs, attributes, galaxy, identity)
    objct = False
    try:
        if event.Object:
            objct = True
    except:
        pass
    if objct:
        for obj in event.Object:
            to_ids = False
            for obj_attr in obj.Attribute:
                if obj_attr.to_ids:
                    to_ids = True
                    break
            obj_name = obj.name
            if obj_name == 'vulnerability':
                addVulnerabilityFromObjects(object_refs, attributes, obj, identity, to_ids)
            else:
                if obj_name in objectsMapping:
                    if to_ids:
                        addIndicatorFromObjects(object_refs, attributes, obj, identity, to_ids)
                    else:
                        addObservedDataFromObject(object_refs, attributes, obj, identity, to_ids)
    return attributes

def handleLink(attribute, external_refs):
    url = attribute.value
    source = 'url'
    if 'comment' in attribute:
        source += ' - {}'.format(attribute.comment)
    link = {'source_name': source, 'url': url}
    external_refs.append(link)


def addAttackPattern(object_refs, attributes, galaxy, identity):
    killchain = [{'kill_chain_name': 'misp-category',
                  'phase_name': galaxy['type']}
                ]
    cluster = galaxy['GalaxyCluster'][0]
    attack_id = "attack-pattern--{}".format(cluster['uuid'])
    name = cluster['value']
    description = cluster['description']
    attack_args = {'id': attack_id, 'type': 'attack-pattern', 'created_by_ref': identity, 'name': name,
                  'description': description, 'kill_chain_phases': killchain}
    if cluster['tag_name']:
        attack_args['labels'] = cluster['tag_name']
    attackPattern = AttackPattern(**attack_args)
    attributes.append(attackPattern)
    object_refs.append(attack_id)

def addCampaign(object_refs, attributes, galaxy, identity):
    cluster = galaxy['GalaxyCluster'][0]
    campaign_id = "campaign--{}".format(cluster['uuid'])
    name = cluster['value']
    description = cluster['description']
    campaign_args = {'id': campaign_id, 'type': 'campaign', 'name': name, 'description': description,
                     'created_by_ref': identity}
    if cluster['tag_name']:
        campaign_args['labels'] = cluster['tag_name']
    meta = cluster['meta']
    addAliases(meta, campaign_args)
    campaign = Campaign(**campaign_args)
    attributes.append(campaign)
    object_refs.append(campaign_id)

def addCourseOfAction(object_refs, attributes, galaxy, identity):
    cluster = galaxy['GalaxyCluster'][0]
    courseOfAction_id = "course-of-action--{}".format(cluster['uuid'])
    name = cluster['value']
    description = cluster['description']
    courseOfAction_args = {'id': courseOfAction_id, 'type': 'course-of-action', 'name': name,
                           'description': description, 'created_by_ref': identity}
    if cluster['tag_name']:
        courseOfAction_args['labels'] = cluster['tag_name']
    courseOfAction = CourseOfAction(**courseOfAction_args)
    attributes.append(courseOfAction)
    object_refs.append(courseOfAction_id)

def addCustomObject(object_refs, attributes, attribute, identity):
    customObject_id = "x-misp-object--{}".format(attribute.uuid)
    timestamp = attribute.timestamp
    customObject_type = 'x-misp-object-{}'.format(attribute.type)
    value = attribute.value
    labels = 'misp:to_ids=\"{}\"'.format(attribute.to_ids)
    customObject_args = {'id': customObject_id, 'x_misp_timestamp': timestamp, 'x_misp_to_ids': labels,
                         'x_misp_value': value, 'created_by_ref': identity}
    if attribute.comment:
        customObject_args['x_misp_comment'] = attribute.comment
    @CustomObject(customObject_type, [('id', properties.StringProperty(required=True)),
                                      ('x_misp_timestamp', properties.StringProperty(required=True)),
                                      ('x_misp_to_ids', properties.StringProperty(required=True)),
                                      ('x_misp_value', properties.StringProperty(required=True)),
                                      ('created_by_ref', properties.StringProperty(required=True)),
                                      ('x_misp_comment', properties.StringProperty()),
                                     ])
    class Custom(object):
        def __init__(self, **kwargs):
            return
    custom = Custom(**customObject_args)
    attributes.append(custom)
    object_refs.append(customObject_id)

def addIdentity(object_refs, attributes, attribute, identity, identityClass):
    identity_id = "identity--{}".format(attribute.uuid)
    name = attribute.value
    identity_args = {'id': identity_id, 'type': 'identity', 'name': name, 'created_by_ref': identity, 'identity_class': identityClass}
    if attribute.comment:
        identity_args['description'] = attribute.comment
    identityObject = Identity(**identity_args)
    attributes.append(identityObject)
    object_refs.append(identity_id)

def addIntrusionSet(object_refs, attributes, galaxy, identity):
    cluster = galaxy['GalaxyCluster'][0]
    intrusionSet_id = "intrusion-set--{}".format(cluster['uuid'])
    name = cluster['value']
    description = cluster['description']
    intrusion_args = {'id': intrusionSet_id, 'type': 'intrusion-set', 'name': name, 'description': description,
                      'created_by_ref': identity}
    meta = cluster['meta']
    if "synonyms" in meta:
        addAliases(meta, intrusion_args)
    if cluster['tag_name']:
        intrusion_args['labels'] = cluster['tag_name']
    intrusionSet = IntrusionSet(**intrusion_args)
    attributes.append(intrusionSet)
    object_refs.append(intrusionSet_id)

def addMalware(object_refs, attributes, galaxy, identity):
    killchain = [{'kill_chain_name': 'misp-category',
                  'phase_name': galaxy['type']}
                 ]
    cluster = galaxy['GalaxyCluster'][0]
    malware_id = "malware--{}".format(cluster['uuid'])
    name = cluster['value']
    description = cluster['description']
    malware_args = {'id': malware_id, 'type': 'malware', 'name': name, 'description': description,
                    'created_by_ref': identity, 'kill_chain_phases': killchain}
    if cluster['tag_name']:
        malware_args['labels'] = cluster['tag_name']
    malware = Malware(**malware_args)
    attributes.append(malware)
    object_refs.append(malware_id)

#def addNote(object_refs, attributes, attribute, identity):         ## SEEMS LIKE IT WILL APPEAR IN THE ##
#    note_id = "note--{}".format(attribute['uuid'])                 ##          UPCOMMING CHANGES       ##
#    note_args = {}
#    note = Note(**note_args)
#    attributes.append(note)
#    object_refs.append(note)

def addObservedData(object_refs, attributes, attribute, identity):
    observedData_id = "observed-data--{}".format(attribute.uuid)
    timestamp = attribute.timestamp
    labels = 'misp:to_ids=\"{}\"'.format(attribute.to_ids)
    observedData_args = {'id': observedData_id, 'type': 'observed-data', 'number_observed': 1, 'labels': labels,
                         'first_observed': timestamp, 'last_observed': timestamp, 'created_by_ref': identity,
                         'objects': defineObservableObject(attribute.type, attribute.value)}
    observedData = ObservedData(**observedData_args)
    attributes.append(observedData)
    object_refs.append(observedData_id)

def addThreatActor(object_refs, attributes, galaxy, identity):
    cluster = galaxy['GalaxyCluster'][0]
    threatActor_id = "threat-actor--{}".format(cluster['uuid'])
    name = cluster['value']
    description = cluster['description']
    threatActor_args = {'id': threatActor_id, 'type': 'threat-actor', 'name': name, 'description': description,
                        'created_by_ref': identity}
    meta = cluster['meta']
    if 'synonyms' in meta:
        addAliases(meta, threatActor_args)
    if cluster['tag_name']:
        threatActor_args['labels'] = cluster['tag_name']
    threatActor = ThreatActor(**threatActor_args)
    attributes.append(threatActor)
    object_refs.append(threatActor_id)

def addTool(object_refs, attributes, galaxy, identity):
    killchain = [{'kill_chain_name': 'misp-category',
                  'phase_name': galaxy['type']}
                 ]
    cluster = galaxy['GalaxyCluster'][0]
    tool_id = "tool--{}".format(cluster['uuid'])
    name = cluster['value']
    description = cluster['description']
    tool_args = {'id': tool_id, 'type': 'tool', 'name': name, 'description': description,
                 'created_by_ref': identity, 'kill_chain_phases': killchain}
    if cluster['tag_name']:
        tool_args['labels'] = cluster['tag_name']
    tool = Tool(**tool_args)
    attributes.append(tool)
    object_refs.append(tool_id)

def addVulnerability(object_refs, attributes, attribute, identity):
    vuln_id = "vulnerability--{}".format(attribute.uuid)
    name = attribute.value
    ext_refs = [{'source_name': 'cve',
                 'external_id': name}]
    labels = 'misp:to_ids=\"{}\"'.format(attribute.to_ids)
    vuln_args = {'type': 'vulnerability', 'id': vuln_id, 'external_references': ext_refs, 'name': name,
                 'created_by_ref': identity, 'labels': labels}
    vulnerability = Vulnerability(**vuln_args)
    attributes.append(vulnerability)
    object_refs.append(vuln_id)

def addIndicatorFromObjects(object_refs, attributes, obj, identity, to_ids):
    indicator_id = 'indicator--{}'.format(obj.uuid)
    category = obj['meta-category']
    killchain = [{'kill_chain_name': 'misp-category',
                  'phase_name': category}]
    labels = 'misp:to_ids=\"{}\"'.format(to_ids)
    pattern = definePatternForObjects(obj.name, obj.Attribute)
    timestamp = getDateFromTimestamp(int(obj.timestamp))
    indicator_args = {'valid_from': timestamp, 'type': 'indicator', 'labels': labels,
                      'pattern': [pattern], 'id': indicator_id,
                      'created_by_ref': identity, 'kill_chain_phases': killchain, 'description': obj.description}
    indicator = Indicator(**indicator_args)
    attributes.append(indicator)
    object_refs.append(indicator_id)

def addObservedDataFromObject(object_refs, attributes, obj, identity, to_ids):
    observedData_id = 'observed-data--{}'.format(obj.uuid)
    timestamp = getDateFromTimestamp(int(obj.timestamp))
    labels = 'misp:to_ids=\"{}\"'.format(to_ids)
    observedData_args = {'id': observedData_id, 'type': 'observed-data', 'number_observed': 1, 'labels': labels,
                         'first_observed': timestamp, 'last_observed': timestamp, 'created_by_ref': identity,
                         'objects': defineObservableObjectForObjects(obj.name, obj.Attribute)}
    observedData = ObservedData(**observedData_args)
    attributes.append(observedData)
    object_refs.append(observedData_id)

def addVulnerabilityFromObjects(object_refs, attributes, obj, identity, to_ids):
    vuln_id = 'vulnerability--{}'.format(obj.id)
    name = 'Undefined name'
    for obj_attr in obj.Attribute:
        if obj_attr.type == 'vulnerability':
            name = obj_attr.value
            break
    labels = 'misp:to_ids=\"{}\"'.format(to_ids)
    vuln_args = {'id': vuln_id, 'type': 'vulnerability', 'name': name, 'created_by_ref': identity,
                 'labels': labels}
    vulnerability = Vulnerability(**vuln_args)
    attributes.append(vulnerability)
    object_refs.append(vuln_id)

def addAliases(meta, argument):
    aliases = []
    for a in meta['synonyms']:
        aliases.append(a)
    argument['aliases'] = aliases

def handleNonIndicatorAttribute(object_refs, attributes, attribute, identity):
    attr_type = attribute.type
    if attr_type == "vulnerability":
        addVulnerability(object_refs, attributes, attribute, identity)
    else:
        addObservedData(object_refs, attributes, attribute, identity)

def handleIndicatorAttribute(object_refs, attributes, attribute, identity):
    indic_id = "indicator--{}".format(attribute.uuid)
    category = attribute.category
    killchain = [{'kill_chain_name': 'misp-category',
                 'phase_name': category}]
    labels = 'misp:to_ids=\"{}\"'.format(attribute.to_ids)
    attr_type = attribute.type
    attr_val = attribute.value
    indicator_args = {'valid_from': attribute.timestamp, 'type': 'indicator',
                      'labels': labels, 'pattern': definePattern(attr_type, attr_val), 'id': indic_id,
                      'created_by_ref': identity, 'kill_chain_phases': killchain}
    if attribute.comment:
        indicator_args['description'] = attribute.comment
    indicator = Indicator(**indicator_args)
    attributes.append(indicator)
    object_refs.append(indic_id)

def buildRelationships(attributes, object_refs):
    return

def defineObservableObject(attr_type, attr_val):
    observed_object = mispTypesMapping[attr_type]['observable'].copy()
    object0 = observed_object['0']
    if '|' in attr_type:
        _, attr_type2 = attr_type.split('|')
        attr_val1, attr_val2 = attr_val.split('|')
        object1 = observed_object['1']
        if '|ip' in attr_type:
            addr_type = defineAddressType(attr_val2)
            object0['value'] = attr_val1
            object1['type'] = addr_type
            object1['value'] = attr_val2
        elif 'ip-' in attr_type:
            addr_type = defineAddressType(attr_val2)
            object0['type'] = addr_type
            object0['value'] = attr_val1
            object1['dst_port'] = attr_val2
        elif 'hostname' in attr_type:
            object0['value'] = attr_val1
            object1['dst_port'] = attr_val2
        elif 'regkey' in attr_type:
            object0['key'] = attr_val1
            object0['values']['name'] = attr_val2
        else:
            object0['name'] = attr_val1
            object0['hashes'] = {attr_type2: attr_val2}
    elif attr_type == 'malware-sample':
        attr_val1, attr_val2 = attr_val.split('|')
        object0['name'] = attr_val1
        object0['hashes'] = {'md5': attr_val2}
    else:
        if 'x509' in attr_type:
            object0['hashes']['sha1'] = attr_val
            return observed_object
        elif 'ip-' in attr_type:
            addr_type = defineAddressType(attr_val)
            object0['type'] = addr_type
        for obj_attr in object0:
            if obj_attr in ('name', 'value', 'body', 'subject', 'dst_port', 'key'):
                object0[obj_attr] = attr_val
            if 'hashes' in obj_attr:
                object0[obj_attr] = {attr_type: attr_val}
    return observed_object

def defineObservableObjectForObjects(obj_name, obj_attr):
    if obj_name == 'email':
        return defineObservableObjectEmail(obj_name, obj_attr)
    elif obj_name == 'domain-ip':
        return definObservableObjectDomainIp(obj_name, obj_attr)
    elif obj_name == 'ip|port':
        return defineObservableObjectIpPort(obj_name, obj_attr)
    elif obj_name == 'registry-key':
        return defineObservableObjectRegKey(obj_name, obj_attr)
    else:
        return defineObservableObjectBasicCase(obj_name, obj_attr)

def defineObservableObjectEmail(obj_name, obj_attr):
    obj = objectsMapping['email']['observable']
    email_attr = getEmailObjectInfo(obj_attr)
    is_multipart = False
    part_number = 1
    if 'email-src' in email_attr:
        email_src = email_attr['email-src']
        part = str(part_number)
        obj[part] = {'type': 'email-addr', 'value': email_src}
        if 'email-src-display-name' in email_attr:
            src_dspl_name = email_attr['email-src-display-name']
            obj[part]['display_name'] = src_dspl_name
        obj['0'][objectTypes['email-src']] = '{}'.format(part)
        part_number += 1
    if 'email-dst' in email_attr:
        if 'to' in email_attr['email-dst']:
            to_type = objectTypes['email-dst']['to']
            email_to = email_attr['email-dst']['to']
            obj['0'][to_type] = []
            for to in email_to:
                part = str(part_number)
                obj[part] = {'type': 'email-addr', 'value': to}
                obj['0'][to_type].append(part)
                part_number += 1
        if 'cc' in email_attr['email-dst']:
            cc_type = objectTypes['email-dst']['cc']
            email_cc = email_attr['email-dst']['cc']
            obj['0'][cc_type] = []
            for cc in email_cc:
                part = str(part_number)
                obj[part] = {'type': 'email-addr', 'value': cc}
                obj['0'][cc_type].append(part)
                part_number += 1
    # if 'email-dst-display-name' in email_attr:
    #     dspl_name = email_attr['email-dst-display-name']
    #     to_type = objectTypes['email-dst']['to']
    #     if to_type not in obj['0']:
    #         obj['0'][to_type] = []
    #     for name in dspl_name:
    #         part = str(part_number)
    #         obj[part] = {'type': 'email-addr', 'display_name': name}
    #         obj['0'][to_type].append(part)
    #         part_number += 1
    if 'email-attachment' in email_attr:
        email_attachmnt = email_attr['email-attachment']
        is_multipart = True
        obj['0']['body_multipart'] = []
        for attachmnt in email_attachmnt:
            part = str(part_number)
            content = 'attachment; filename=\'{}\''.format(attachmnt)
            body_multipart = {'content_disposition': content, 'body_raw_ref': part}
            obj['0']['body_multipart'].append(body_multipart)
            obj[part] = {'type': 'file', 'name': attachmnt}
            part_number += 1
    obj['0']['is_multipart'] = is_multipart
    if 'email-x-mailer' in email_attr:
        x_mailer = email_attr['email-x-mailer']
        obj['0']['additional_header_fields'] = {'x-mailer': x-mailer}
    if 'email-reply-to' in email_attr:
        reply_to = email_attr['email-reply-to']
        try:
            obj['0']['additional_header_fields']['reply-to'] = reply_to
        except KeyError:
            obj['0']['additional_header_fields'] = {'reply-to': reply_to}
    if 'email-subject' in email_attr:
        subject = email_attr['email-subject']
        obj['0'][objectTypes['email-subject']] = subject
    return obj

def defineObservableObjectDomainIp(obj_name, obj_attr):
    obj = mispTypesMapping['domain|ip']['observable']
    for attr in obj_attr:
        attr_type = attr.type
        if attr_type == 'domain':
            obj['0']['value'] = attr.value
        elif attr_type == 'ip-dst':
            attr_val = attr.value
            obj['1']['type'] = defineAddressType(attr_val)
            obj['1']['value'] = attr_val
    return obj

def defineObservableObjectIpPort(obj_name, obj_attr):
    obj = mispTypesMapping['ip-dst|port']['observable']
    for attr in obj_attr:
        attr_type = attr.type
        if attr_type == 'ip-dst':
            attr_val = attr.value
            obj['0']['type'] = defineAddressType(attr_val)
            obj['0']['value'] = attr_val
        elif attr_type in ('text', 'datetime'):
            obj_relation = attr.object_relation
            if obj_name not in objectTypes[attr_type]:
                continue
            obj['1'][objectTypes[attr_type][obj_name][obj_relation]] = attr.value
        else:
            obj['1'][objectTypes[attr_type][attr.object_relation]] = attr.value
    return obj

def defineObservableObjectRegKey(obj_name, obj_attr):
    obj = objectsMapping[obj_name]['observable']
    reg_attr = getRegistryKeyInfo(obj_attr)
    if 'reg-key' in reg_attr:
        key_type = objectTypes['reg-key']
        key = reg_attr['reg-key']
        obj['0'][key_type] = key
    if 'datetime' in reg_attr:
        date_type = objectTypes['datetime'][obj_name]
        date = reg_attr['datetime']
        obj['0'][date_type] = date
    val = False
    values = {}
    for o in ('reg-datatype', 'reg-data', 'reg-name'):
        if o in reg_attr:
            o_type = objectTypes[o]
            o_val = reg_attr[o]
            values[o_type] = o_val
            val = True
    if val:
        obj['0']['values'] = [values]
    return obj

def defineObservableObjectBasicCase(obj_name, obj_attr):
    obj = objectsMapping[obj_name]['observable']
    for attr in obj_attr:
        attr_type = attr.type
        if 'md5' in attr_type or 'sha' in attr_type or 'hash' in attr_type or 'ssdeep' in attr_type:
            obj['0']['hashes'][attr_type] = attr.value
        elif attr_type in ('text', 'datetime'):
            obj_relation = attr.object_relation
            if obj_name not in objectTypes[attr_type] or obj_relation not in objectTypes[attr_type][obj_name]:
                continue
            obj['0'][objectTypes[attr_type][obj_name][obj_relation]] = attr.value
        else:
            if attr_type in objectTypes:
                obj['0'][objectTypes[attr_type]] = attr.value
    return obj

def getEmailObjectInfo(obj_attr):
    email_attr = {}
    for attr in obj_attr:
        attr_type = attr.type
        if attr_type == 'email-dst':
            try:
                email_attr[attr_type][attr.object_relation].append(attr.value)
            except KeyError as key:
                if 'email-dst' not in email_attr:
                    email_attr[attr_type] = {attr.object_relation: [attr.value]}
                else:
                    email_attr[attr_type].update({attr.object_relation: [attr.value]})
        elif attr_type in ('email-dst-display-name', 'email-attachment'):
            try:
                email_attr[attr_type].append(attr.value)
            except:
                email_attr[attr_type] = [attr.value]
        else:
            email_attr[attr_type] = attr.value
    return email_attr

def getRegistryKeyInfo(obj_attr):
    reg_attr = {}
    for attr in obj_attr:
        attr_type = attr.type
        reg_attr[attr_type] = attr.value
    return reg_attr

def definePattern(attr_type, attr_val):
    if '|' in attr_type:
        attr_type1, attr_type2 = attr_type.split('|')
        attr_val1, attr_val2 = attr_val.split('|')
        if 'ip-' in attr_type1 or 'ip' in attr_type2:
            addr_type = defineAddressType(attr_val2)
            pattern = mispTypesMapping[attr_type]['pattern'].format(attr_val1, attr_val2, addr_type)
        else:
            pattern = mispTypesMapping[attr_type]['pattern'].format(attr_val1, attr_val2)
    elif attr_type == 'malware-sample':
        attr_val1, attr_val2 = attr_val.split('|')
        pattern = mispTypesMapping[attr_type]['pattern'].format(attr_val1, attr_val2)
    else:
        if 'ip-' in attr_type:
            addr_type = defineAddressType(attr_val)
            pattern = mispTypesMapping[attr_type]['pattern'].format(addr_type, attr_val)
        else:
            pattern = mispTypesMapping[attr_type]['pattern'].format(attr_val)
    return [pattern]

def definePatternForObjects(obj_name, obj_attr):
    pattern = ''
    if obj_name == 'email':
        for attr in obj_attr:
            attr_type = attr.type
            attr_val = attr.value
            if 'display-name' in attr_type:
                emailType = 'addr'
                attrType = 'display_name'
            else:
                emailType = 'message'
                if attr_type == 'email-dst':
                    obj_relation = attr.object_relation
                    attrType = objectTypes[attr_type][obj_relation]
                elif attr_type == 'datetime':
                    attrType = objectTypes[attr_type][obj_name]
                else:
                    attrType = objectTypes[attr_type]
            pattern += objectsMapping[obj_name]['pattern'].format(emailType, attrType, attr_val)
    elif obj_name == 'ip|port' or obj_name == 'domain-ip':
        for attr in obj_attr:
            attr_type = attr.type
            attr_val = attr.value
            if attr_type == 'ip-dst':
                addr_type = defineAddressType(attr_val)
                attrType = objectTypes[attr_type][obj_name].format(addr_type)
            elif attr_type in ('text', 'datetime'):
                obj_relation = attr.object_relation
                if obj_name not in objectTypes[attr_type]:
                    continue
                attrType = objectTypes[attr_type][obj_name][obj_relation]
            else:
                obj_relation = attr.object_relation
                attrType = objectTypes[attr_type][obj_relation]
            pattern += objectsMapping[obj_name]['pattern'].format(attrType, attr_val)
    else:
        for attr in obj_attr:
            attr_type = attr.type
            attr_val = attr.value
            if 'md5' in attr_type or 'sha' in attr_type or 'hash' in attr_type or 'ssdeep' in attr_type:
                attrType = objectTypes['hashes'].format(attr_type)
            elif attr_type in ('text', 'datetime'):
                obj_relation = attr.object_relation
                if obj_name not in objectTypes[attr_type] or obj_relation not in objectTypes[attr_type][obj_name]:
                    continue
                attrType = objectTypes[attr_type][obj_name][obj_relation]
            elif attr_type in noChangesTypes:
                attrType = attr_type
            else:
                if attr_type not in objectTypes:
                    continue
                attrType = objectTypes[attr_type]
            pattern += objectsMapping[obj_name]['pattern'].format(attrType, attr_val)
    return pattern[:-5]

def defineAddressType(attr_val):
    if ':' in attr_val:
        addr_type = 'ipv6-addr'
    else:
        addr_type = 'ipv4-addr'
    return addr_type

def eventReport(event, identity, object_refs, external_refs):
    timestamp = event.publish_timestamp
    name = event.info
    labels = []
    if 'Tag' in event:
        tags = event.Tag
        for tag in tags:
            labels.append(tag['name'])

    args_report = {'type': "report", 'id': "report--{}".format(event.uuid), 'created_by_ref': identity,
                    'name': name, 'published': timestamp}

    if labels:
        args_report['labels'] = labels
    else:
        args_report['labels'] = ['threat-report']
    if object_refs:
        args_report['object_refs'] = object_refs
    if external_refs:
        args_report['external_references'] = external_refs
    report = Report(**args_report)
    return report

def generateEventPackage(event, SDOs):
    bundle_id = event.uuid
    bundle_args = {'type': "bundle", 'spec_version': "2.0", 'id': "bundle--{}".format(bundle_id), 'objects': SDOs}
    bundle = Bundle(**bundle_args)
    return bundle

def main(args):
    pathname = os.path.dirname(sys.argv[0])
    if len(sys.argv) > 3:
        namespace[0] = sys.argv[3]
    if len(sys.argv) > 4:
        namespace[1] = sys.argv[4].replace(" ", "_")
        namespace[1] = re.sub('[\W]+', '', namespace[1])
    misp = pymisp.MISPEvent(None, False)
    misp.load_file(os.path.join(pathname, args[1]))
    SDOs = []
    object_refs = []
    external_refs = []
    identity = setIdentity(misp, SDOs)
    attributes = readAttributes(misp, identity, object_refs, external_refs)
    buildRelationships(attributes, object_refs)
    report = eventReport(misp, identity, object_refs, external_refs)
    SDOs.append(report)
    for attribute in attributes:
        SDOs.append(attribute)
    stix_package = generateEventPackage(misp, SDOs)
    saveFile(args, pathname, stix_package)
    print(1)

if __name__ == "__main__":
    main(sys.argv)
