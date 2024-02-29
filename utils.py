#!/usr/bin/env python
# coding: utf-8
import numpy as np
import random
import torch


def set_random_seed(seed=0):
    """Set random/np.random/torch.random/cuda.random seed.
    Parameters
    ----------
    seed : int
        Random seed to use
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)


def cos_sim(pairs):
    from torch.nn.functional import cosine_similarity
    return cosine_similarity(pairs[0], pairs[1]).mean()


def sim_loss(pos_pairs, embeddings):
    embedding_pairs = embeddings[pos_pairs]
    loss = -1*cos_sim(embedding_pairs)
    return loss


def mutual_info(x, x_aug, temperature=0.2, sym=True):
    batch_size = x.shape[0]
    x_abs = x.norm(dim=1)
    x_aug_abs = x_aug.norm(dim=1)

    sim_matrix = torch.einsum('ik,jk->ij', x, x_aug) / torch.einsum('i,j->ij', x_abs, x_aug_abs)

    sim_matrix = torch.exp(sim_matrix / temperature)
    pos_sim = sim_matrix[range(batch_size), range(batch_size)]

    if sym:

        loss_0 = pos_sim / (sim_matrix.sum(dim=0) - pos_sim)
        loss_1 = pos_sim / (sim_matrix.sum(dim=1) - pos_sim)
    #    print(pos_sim,sim_matrix.sum(dim=0))
        loss_0 = - torch.log(loss_0).mean()
        loss_1 = - torch.log(loss_1).mean()
        loss = (loss_0 + loss_1) / 2.0
    else:
        loss = pos_sim / (sim_matrix.sum(dim=1) - pos_sim)
        loss = - torch.log(loss).mean()

    return loss


def q_distribute(Z: torch.Tensor, cluster_centers):
    """
    calculate the soft assignment distribution based on the embedding and the cluster centers
    Args:
        Z: fusion node embedding
    Returns:
        the soft assignment distribution Q
    """
    q = 1.0 / (1.0 + torch.sum(torch.pow(Z.unsqueeze(1) - cluster_centers, 2), 2))
    assert q.min() > 0
    q = (q.t() / torch.sum(q, 1)).t()
    return q


def target_distribution(Q):
    """
    calculate the target distribution (student-t distribution)
    Args:
        Q: the soft assignment distribution
    Returns: target distribution P
    """
    weight = Q ** 2 / Q.sum(0)
    P = (weight.t() / weight.sum(1)).t()
    return P


def cluster_acc(y_true, y_pred):
    """
    calculate clustering acc and f1-score
    Args:
        y_true: the ground truth
        y_pred: the clustering id

    Returns: acc and f1-score
    """
    from sklearn import metrics
    from munkres import Munkres
    y_min = np.min(y_true)
    y_true = y_true - y_min
    l1 = list(set(y_true))
    num_class1 = len(l1)
    l2 = list(set(y_pred))
    num_class2 = len(l2)
    ind = 0
    if num_class1 != num_class2:
        for i in l1:
            if i in l2:
                pass
            else:
                y_pred[ind] = i
                ind += 1
    l2 = list(set(y_pred))
    numclass2 = len(l2)
    if num_class1 != numclass2:
        print('error')
        return
    cost = np.zeros((num_class1, numclass2), dtype=int)
    for i, c1 in enumerate(l1):
        mps = [i1 for i1, e1 in enumerate(y_true) if e1 == c1]
        for j, c2 in enumerate(l2):
            mps_d = [i1 for i1 in mps if y_pred[i1] == c2]
            cost[i][j] = len(mps_d)
    m = Munkres()
    cost = cost.__neg__().tolist()
    indexes = m.compute(cost)
    new_predict = np.zeros(len(y_pred))
    for i, c in enumerate(l1):
        c2 = l2[indexes[i][1]]
        ai = [ind for ind, elm in enumerate(y_pred) if elm == c2]
        new_predict[ai] = c
    acc = metrics.accuracy_score(y_true, new_predict)
    f1_macro = metrics.f1_score(y_true, new_predict, average='macro')
    return acc, f1_macro


def eva(y_true, y_pred, show_details=True):
    """
    evaluate the clustering performance
    Args:
        y_true: the ground truth
        y_pred: the predicted label
        show_details: if print the details
    Returns: None
    """
    from sklearn.metrics import adjusted_rand_score as ari_score
    from sklearn.metrics.cluster import normalized_mutual_info_score as nmi_score
    acc, f1 = cluster_acc(y_true, y_pred)
    nmi = nmi_score(y_true, y_pred, average_method='arithmetic')
    ari = ari_score(y_true, y_pred)
    if show_details:
        print(':acc {:.4f}'.format(acc), ', nmi {:.4f}'.format(nmi), ', ari {:.4f}'.format(ari),
              ', f1 {:.4f}'.format(f1))
    return acc, nmi, ari, f1


def cluster_and_evaluate(Z, y, n_clusters):
    from sklearn.cluster import KMeans
    """
    clustering based on embedding
    Args:
        Z: the input embedding
        y: the ground truth
        n_clusters: number of clusters
    Returns: acc, nmi, ari, f1, clustering centers
    """
    y = np.array(y.to('cpu'))
    model = KMeans(n_clusters, n_init=20)
    cluster_id = model.fit_predict(Z.data.cpu().numpy())
    acc, nmi, ari, f1 = eva(y, cluster_id, False)
    return acc, nmi, ari, f1, model.cluster_centers_