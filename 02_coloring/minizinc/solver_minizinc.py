#!/usr/bin/python
# -*- coding: utf-8 -*-

# The MIT License (MIT)
#
# Copyright (c) 2014 Andrea Rendl
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.


# -------------------------------------------------------------------------------
#     ABOUT THE MINIZINC SOLVER:
# -------------------------------------------------------------------------------
#
# ABOUT MINIZINC:
#
# Minizinc is a highlevel modelling language in which it is easy to formulate
# problems. A problem formulation consists of a problem model (.mzn file) 
# and a data file (.dzn file). Given a problem and a data file, the Minizinc tool
# can translate the problem into a MIP model or CP model and forwards it to a 
# solver. This is very convenient for the user, since she/he does not have to deal
# with the solver input format.
#
# ABOUT THIS SOLVER:
# 
# The problem model for the set covering problem can be found in the file 
# 'setCovering.mzn'. This script automatically generates the Minizinc data file 
# for a given problem instance, and writes it into the file 'data.dzn'. The two
# files are then forwarded to a MIP solver (CBC from COIN-OR) and solved. The 
# solver output is read and converted into the submission output format.
#
# -------------------------------------------------------------------------------
#    HOW TO USE THIS SOLVER:
# -------------------------------------------------------------------------------
# 
# + Download and install Minizinc: http://www.minizinc.org/
#
# + Make sure that the Minizinc binaries are part of your PATH. 
#   To achieve that, enter the following into your shell (or add it to your 
#   ~/.bashrc or equivalent):
#       export PATH=$PATH:/your/path/to/minizinc/bin/
# 
# + Execute the solver just like the standard solver. For instance:
#   python solver_minizinc.py data/sc_25_0
#
# + If you want to play around with the solver: 
#   + You can change the maximum number of solutions that the solver will search 
#     for in this script (search for 'nb_solutions').
#   + There are different kinds of solvers that you can use for solving 
#     the problem: a MIP solver and 3 different CP solvers. To play around with 
#     them, uncomment the right lines for invoking the Minizinc process (search 
#     for 'ALTERNATIVE' is this file).
#
# + There are many other Minizinc examples in the /examples directory of your
#   Minizinc installation.
# 
# -------------------------------------------------------------------------------
#    GETTING HELP
# -------------------------------------------------------------------------------
#
# + If you need any help, have a look at the Discussion forum of the course and
#   post your questions. Make sure that nobody has asked your question already!
#
# -------------------------------------------------------------------------------

# solver adapted to run minizinc
# https://github.com/discreteoptimization/setcover/blob/master/minizinc_001/solver.py

import os, signal
from subprocess import Popen, check_output, PIPE, TimeoutExpired
import networkx as nx
from networkx.algorithms.approximation import clique
import matplotlib.pyplot as plt 
import statistics 
import math
import random
#import time

DEBUG = True

def solve_it(input_data):
    # parse the input
    lines = input_data.split('\n')

    parts = lines[0].split()
    node_count = int(parts[0])
    edge_count = int(parts[1])
    
    edges = []
    for i in range(1, edge_count+1):
        parts = lines[i].split()
        edges.append((int(parts[0]), int(parts[1])))

    # generate NetworkX graph
    G = nxGraph(edges)

    # set variables for process communication with minizinc
    process = None
    stdout = None
    stderr = None

    # find the max_clique as a lower bound. at least this number of colors are required
    max_clique = [1]
    if node_count <= 500:
        # not recommended for graphs with more than 500 nodes
        max_clique = clique.max_clique(G)
    if DEBUG:
        print ('max_clique:', len(max_clique), max_clique)
        
    # According to the book: "A Guide to Graph Colouring: Algorithms and Applications", 
    #  Section '2.2.2 Upper bounds',  the max degree can be used as an upper bound
    degrees = [0]*node_count
    for node in range(node_count):
        degrees.append(G.degree(node)+1)
    #remove the zeros from the list
    while 0 in degrees: degrees.remove(0)
    max_degree = max(degrees)
    if DEBUG:
        print ('max_degree:', max_degree, degrees)
    lb = len(max_clique)
    ub = lb
    timeout = 30
    # the states are 'timeout', 'nsat', 'sat'
    minizinc_state = None
    while True:
        if DEBUG:
            print ("running with lb:", lb, "and ub:", ub)
        # generate MiniZinc data file
        data_file = "data.dzn"
        generateMinizincDataFile(node_count, edge_count, lb, ub, edges, data_file)

        # solve with Minizinc's MIP solver (CBC of COIN-OR)
        minizinc_proc = Popen(['minizinc', '-m', 'graphColoring.mzn', '-d', 'data.dzn'],
                stdout=PIPE, stderr=PIPE)
        try:
            (stdout, stderr) = minizinc_proc.communicate(timeout=timeout)
        except TimeoutExpired as exc:
            os.killpg(os.getpgid(minizinc_proc.pid), signal.SIGTERM) 
            minizinc_proc.kill()
            #time.sleep(1)
            minizinc_state = 'timeout'
        # any other exception
        except Exception as e:
            minizinc_proc.kill()
            #time.sleep(1)
            minizinc_state = 'exception'
        else:
            aborted = False
            # solution found, can abort the while loop
            if DEBUG:
                print ("solution found")
                print (stdout)
                print (stderr)
            satisfied = str(stdout, 'utf-8')
            lines = satisfied.split('\n')
            # continue the search if it is not satisfied with these bounds
            if 'UNSATISFIABLE' in lines[0]:
                minizinc_state = 'nsat'
            else:
                minizinc_state = 'sat'

        if minizinc_state == 'timeout':
            # the problem is too big for this time out
            print ("It wasnt possible to execute with the timeout,", timeout)
            break
        elif minizinc_state == 'exception':
            print ("Unknown error occured")
            break
        elif minizinc_state == 'nsat':
            if lb < max_degree:
                lb +=1
                ub +=1
            else:
                # abort because all reached the true upper bound. nothing else to search
                print ("upper bound reached and no solution was found")
                break
        else:
            # solution found !
            break

    output_data = None
    if minizinc_state == 'sat':
        # extract the solution from standard-out
        colors, solution = extractSolution(stdout,node_count)

        if DEBUG:
            # generate the colored graph
            graph_dot(G, int(colors), solution)

        # prepare the solution in the specified output format
        output_data = str(colors) + ' ' + str(1) + '\n'
        output_data += ' '.join(map(str, solution))
    else:
        print ("Aborted!")

    return output_data

###################################################################################
def nxGraph(edges):
    """ It generates a Networkx graph.
    """
    G = nx.Graph()

    for e in edges:
        G.add_edge(e[0], e[1])
    
    return G

###################################################################################
def graph_dot(G, colors, solution):
    """ It generates graphviz graphs.
    """

    if DEBUG:
        print ('writing the graph ...')
    # open the color file
    color_file = open('svg_colors', 'r')
    color_data = ''.join(color_file.readlines())
    color_file.close()
    lines = color_data.split('\n')
    # remove the trailing white spaces
    lines = [ele.replace(' ', '') for ele in lines]
    lines = [ele.replace('\t', '') for ele in lines]

    selected_colors = []
    # randomly select a set of colors
    i = colors
    while i>0:
        new_color = lines[random.randint(0, len(lines)-1)]
        if new_color not in selected_colors:
            selected_colors.append(new_color)
            i -=1

    if DEBUG:
        print ('selected colors:', selected_colors)
        print ('solution:', solution)

    # transforms NetworkX into PyG AGraph
    A = nx.nx_agraph.to_agraph(G)

    for i in range(len(solution)):
        n=A.get_node(i)
        color_code = solution[i]-1
        n.attr['fillcolor'] = selected_colors[color_code]
        n.attr['style']='filled'

    # create the legend
    legend_nodes = []
    for i in range(len(selected_colors)):
        node_name = 'c'+str(i)
        A.add_node(node_name)
        n=A.get_node(node_name)
        n.attr['fillcolor'] = selected_colors[i]
        legend_nodes.append(node_name)
        n.attr['style']='filled'
    A.add_subgraph(name='cluster1', nbunch= legend_nodes, label='legend', color = 'black', rank='same')

    A.write("graph.dot")
    A.layout(prog='dot')
    A.draw("graph.png")

###################################################################################
# not working. it misses some form of auto color assignment
def graph_pyplot(G, colors, solution):

    for n in G.nodes():
        color_code = solution[n]-1
        G.nodes[n]['color'] = selected_colors[color_code]

    nx.draw(G, with_labels = True) 
    plt.savefig("graph.svg") 

###################################################################################
def generateMinizincDataFile(node_count, edge_count, lb, ub, edges, data_file):
    tmpFile = open(data_file, 'w')
    
    out = "% automatically generated Minizinc data file\n"
    out += "ubc = " + str(ub)+ ";\n"
    out += "lbc = " + str(lb)+ ";\n"
    out += "nbNodes = " + str(node_count)+ ";\n"
    out += "nbEdges = " + str(edge_count)+ ";\n"
    out += "edges1 = [ " 
    cnt = 0
    for s in edges: 
        out += str(int(s[0]))
        if cnt == len(edges)-1:
            out += "];\n"
        else: 
            out += ", "
        cnt += 1
    out += "edges2 = [ " 
    cnt = 0
    for s in edges: 
        out += str(int(s[1]))
        if cnt == len(edges)-1:
            out += "];\n"
        else: 
            out += ", "
        cnt += 1

    tmpFile.write(out)
    tmpFile.close()
# ##################################################################################
def extractSolution(stdout,node_count):
    solution = [0]*node_count
    
    stdout = str(stdout, 'utf-8')
    lines = stdout.split('\n')   
    nColors = lines[0]
    line = lines[1]
    # the second line is expected in this format
    # [1, 0, 1, 1]
    # remove the 1st and the last char
    line = line[1:-1]
    words = line.split(', ')
    if len(words) != node_count:
        print ("Error in number of solutions")
    else:
        for i in range(0,len(words)):
            solution[i] = int(words[i])

    return nColors, solution

# ##################################################################################        
import sys

if __name__ == '__main__':
    if len(sys.argv) > 1:
        file_location = sys.argv[1].strip()
        input_data_file = open(file_location, 'r')
        input_data = ''.join(input_data_file.readlines())
        input_data_file.close()
        print ('Solving:', file_location)
        print (solve_it(input_data))
    else:
        print ('This test requires an input file.  Please select one from the data directory. (i.e. python solver.py ./data/sc_6_1)')