#include <bits/stdc++.h>
#include <omp.h>
using namespace std;

/*
 * Given an adjacency matrix for our problem, compute the
 * set of K nearest neighbours for each vertex.
 *
 * Since our edge weighting scheme is "inverse",
 * meaning that "the more - the better", we translate
 * weights to mean "the less - the better".
 *
 * All weights are positive, so we use Dijkstra's algorithm,
 * and terminate it after K steps.
 *
 * Input arguments: 
 *   1 - path to a text file with matrix;
 *   2 - integer K.
 *   3 - path to output file, where we store mapping 
 *      from tag id (from the adjacency matrix)
 *      to tag id (in the neighbour matrix)
 *
 * Output: 
 *   for each vertex, a set of pairs "neighbour_num,distance".
 *   Vertex numbers are normalized to 1..number_of_verices.
 *
 *
 * Example output:
 *   1: 2,0.5 10,493 15,1.1
 *   2: 1,0.5 123,45
 *   ...
 *
 *
 * Complexity: 
 *   not exactly known, something like
 *   O(N^2 * K * log(N)), constant is high due to floating point ops.
 *  
 *
 *  Running time: ~1 hour on full graph.
 */

static pair<int, double> answer[60000][155];

struct dijkstra
{
    dijkstra(string mapping_file_name)
        : mapping_out_(mapping_file_name)
    {
    }

    void find_nearest_neighbours(int vertex_num, int num_of_neighbours)
    {
        auto st = set< pair<double, int> >();

        timer++;
        current_time_[vertex_num] = timer;
        current_distance_[vertex_num] = 0.0;
        st.insert(make_pair(current_distance_[vertex_num], vertex_num));

        int it;
        for (it = 0; it <= num_of_neighbours && not st.empty(); it++)
        {
            auto iter = st.begin();
            int best_vertex = iter->second;
            st.erase(iter);
            for (const auto& edge: adj_list_[best_vertex])
            {
                int to_vertex = edge.first;
                double weight = edge.second;

                if (current_time_[to_vertex] != timer)
                {
                    current_time_[to_vertex] = timer;
                    current_distance_[to_vertex] = inf;
                }

                double cur_dist = current_distance_[to_vertex];
                double proposed_dist = current_distance_[best_vertex] + weight;

                if (proposed_dist < cur_dist)
                {
                    current_distance_[to_vertex] = proposed_dist;
                    st.erase(make_pair(cur_dist, to_vertex));
                    st.insert(make_pair(proposed_dist, to_vertex));
                }

                current_distance_[to_vertex] = min(current_distance_[to_vertex],
                        current_distance_[best_vertex] + weight);
            }

            // First neighbour is always self.
            if (it > 0)
            {
                current_neighbour_indices_[it] = best_vertex;
            }
        }

        // Since t-SNE operates with indices of points,
        // we must preserve every row, even if current vertex
        // does not have needed number of neighbours.
        // Otherwise, t-SNE output will be messed up.
        int cur_idx = 0;
        for (; it <= num_of_neighbours; it++)
        {
            while (current_time_[cur_idx] == timer)
            {
                cur_idx++;
            }
            current_distance_[cur_idx] = inf;
            current_neighbour_indices_[it] = cur_idx;
            cur_idx++;
        }

        if (it == num_of_neighbours + 1)
        {
            cout << vertex_num << ": ";

            for (int i = 1; i <= num_of_neighbours; i++)
            {
                int best_vertex = current_neighbour_indices_[i];
                answer[vertex_num]
                cout << best_vertex << "," << current_distance_[best_vertex] << " ";
            }

            cout << endl;
        }
    }

    void read_graph(const char* path_to_matrix)
    {
        ifstream inp(path_to_matrix);
        string row_representation;
        while (getline(inp, row_representation))
        {
            istringstream ss(row_representation);
            int source_vertex;
            ss >> source_vertex;
            source_vertex = normalize_vertex_num(source_vertex);
            ss.ignore(1);

            int dest_vertex, edge_w;
            while (ss >> dest_vertex)
            {
                dest_vertex = normalize_vertex_num(dest_vertex);
                ss.ignore(1);
                ss >> edge_w;
                double edge_weight = convert_edge_w_to_weight(edge_w);
                adj_list_[source_vertex].push_back(make_pair(dest_vertex, edge_weight));
                adj_list_[dest_vertex].push_back(make_pair(source_vertex, edge_weight));
            }
        }
        cerr << "Preprocessing end" << endl;
    }

    int number_of_verices()
    {
        return vertex_num_to_normalized_num_.size();
    }
private:
    static constexpr double inf = 1e15;
    static const int max_vertices_ = 60000;
    int timer = 0;
    map<int, int> vertex_num_to_normalized_num_;
    vector< pair<int, double> > adj_list_[max_vertices_];
    double current_distance_[max_vertices_];
    int current_time_[max_vertices_];
    int current_neighbour_indices_[max_vertices_];
    ofstream mapping_out_;

    int normalize_vertex_num(int vertex_num)
    {
        if (not vertex_num_to_normalized_num_.count(vertex_num))
        {
            vertex_num_to_normalized_num_[vertex_num] = 
                vertex_num_to_normalized_num_.size() - 1;
            mapping_out_ << vertex_num << " " 
                << vertex_num_to_normalized_num_[vertex_num] << endl;
        }
        return vertex_num_to_normalized_num_[vertex_num];
    }

    double convert_edge_w_to_weight(int edge_w)
    {
        // Possible functions: 1000 / x, exp(-x), 100 / log(x), ...
        return 100 / log(edge_w + 1);
    }
};

int main(int argc, char** argv)
{
    assert(argc == 4);
    auto dij = dijkstra(argv[3]);
    int num_of_neighbours = atoi(argv[2]);
    dij.read_graph(argv[1]);

    int num_vertices = dij.number_of_verices();
#pragma omp parallel for
    for (int i = 0; i < num_vertices; i++)
    {
        dij.find_nearest_neighbours(i, num_of_neighbours);
    }
    return 0;
}