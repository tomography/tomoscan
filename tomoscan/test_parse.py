from xml.dom.minidom import parseString
from epics import PV


def test_parse(xmlFile, macros=[]):

    epicsPVs = {}

    # A valid first line of an xml file will be optional whitespace followed by '<'
    xml_lines = open(xmlFile).read()
    if not(xml_lines.lstrip().startswith("<")):
        print("File does not look like valid XML:")
        print("".join(xml_lines[:2]))
        sys.exit(1)
        
    # Do macro substitution
    for key in macros:
      print("Replacing", key, "with", macros[key])
      xml_lines = xml_lines.replace(key, macros[key])
    
    # parse xml file to dom object
    xml_root = parseString(xml_lines.lstrip())
    
    # function to read element children of a node
    def elements(node):
        return [n for n in node.childNodes if n.nodeType == n.ELEMENT_NODE]  
    
    # a function to read the text children of a node
    def getText(node):
        return ''.join([n.data for n in node.childNodes if n.nodeType == n.TEXT_NODE])
    
    # Parse the nodes
    def handle_node(node):
        if node.nodeName == "Attributes":
            for n in elements(node):
                handle_node(n)
        elif node.hasAttribute("name"):
            name = str(node.getAttribute("name"))
            if node.hasAttribute("type"):
              type = str(node.getAttribute("type"))
            if node.hasAttribute("source"):
              source = str(node.getAttribute("source"))
            if node.hasAttribute("dbrtype"):
              dbrtype = str(node.getAttribute("dbrtype"))
            if node.hasAttribute("description"):
              description = str(node.getAttribute("description"))
            if (name != None) and (source != None) and (type == "EPICS_PV"):
              epicsPVs[name] = PV(source)
        else:
            print("Node has no name attribute", node)
    
    # list of all nodes    
    for node in elements(elements(xml_root)[0]):
        handle_node(node)
    for key in epicsPVs:
      print(key, ":", epicsPVs[key], ":", epicsPVs[key].get(as_string=True))
