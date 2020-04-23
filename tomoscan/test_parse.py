from xml.dom.minidom import parseString
from epics import PV
from collections import namedtuple

class TomoParam(namedtuple('TomoParam', ['name', 'type', 'source', 'dbrtype', 'description', 'pv'])):

  def get(self):
    if (self.dbrtype == "DBR_STRING"):
      self.value = self.pv.get(as_string=True)
    else:
      self.value = self.pv.get()
    return self.value;

def test_parse(xmlFile, macros=[]):

    epicsPVs = {}
    TomoParams = {}

    # A valid first line of an xml file will be optional whitespace followed by '<'
    xml_lines = open(xmlFile).read()
    if not(xml_lines.lstrip().startswith("<")):
        print("File does not look like valid XML:")
        print("".join(xml_lines[:2]))
        sys.exit(1)
        
    # Do macro substitution
    for key in macros:
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
        elif node.nodeName == "Attribute":
            if (node.hasAttribute("name")):
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
              pv = PV(source)
              epicsPVs[name] = pv
              TomoParams[name] = TomoParam(name, type, source, dbrtype, description, pv)
    
    # list of all nodes    
    for node in elements(elements(xml_root)[0]):
        handle_node(node)

    # Print all names and values for debugging
    for key in TomoParams:
      print(key, ":", TomoParams[key].get())
